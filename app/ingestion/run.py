"""Run one ingestion pass across every configured source."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.clean import clean_articles, frame_records
from app.ingestion.dedupe import find_near_duplicate
from app.ingestion.fetch_api import MissingAPIKey, fetch_provider
from app.ingestion.fetch_rss import fetch_feed
from app.ingestion.http import build_session
from app.ingestion.sources_config import FETCH_SOURCES, FetchSource, reliability_for
from app.ingestion.types import RawArticle
from app.models import Article, IngestionRun, Source

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def upsert_source(
    db: Session,
    *,
    domain: str,
    name: str,
    kind: str,
    feed_url: str | None = None,
    country_iso2: str | None = None,
    active: bool = True,
) -> Source:
    """Insert or update a source row keyed by domain."""
    domain = domain.lower().strip()
    tier, score = reliability_for(domain)
    source = db.scalar(select(Source).where(Source.domain == domain))
    if source is None:
        source = Source(
            name=name or domain,
            domain=domain,
            type=kind,
            feed_url=feed_url,
            country_iso2=country_iso2,
            reliability_tier=tier,
            reliability_score=score,
            is_active=active,
            created_at=_now(),
        )
        db.add(source)
        db.flush()
        return source
    source.name = name or source.name
    source.type = kind or source.type
    if feed_url:
        source.feed_url = feed_url
    if country_iso2:
        source.country_iso2 = country_iso2
    source.reliability_tier = tier
    source.reliability_score = score
    if active:
        source.is_active = True
    return source


def _fetch(spec: FetchSource, session) -> list[RawArticle]:
    if spec.kind == "rss":
        if not spec.feed_url:
            return []
        return fetch_feed(spec.feed_url, session, assume_relevant=spec.assume_relevant)
    if not spec.provider:
        return []
    return fetch_provider(spec.provider, session, assume_relevant=spec.assume_relevant)


def _store_batch(db: Session, spec: FetchSource, articles: list[RawArticle]) -> tuple[int, int, int]:
    """Insert cleaned rows. Returns ``(fetched, inserted, duplicates)``."""
    frame = clean_articles(articles)
    records = frame_records(frame)
    fetched = len(records)
    if not records:
        return 0, 0, 0
    hashes = [row["url_hash"] for row in records]
    existing = set(
        db.scalars(select(Article.url_hash).where(Article.url_hash.in_(hashes))).all()
    )
    inserted = 0
    duplicates = 0
    cutoff = _now() - timedelta(hours=48)
    for row in records:
        if row["url_hash"] in existing:
            duplicates += 1
            continue
        if spec.provider in {"newsapi", "gnews"} and row.get("outlet_domain"):
            source = upsert_source(
                db,
                domain=row["outlet_domain"],
                name=row.get("outlet_name") or row["outlet_domain"],
                kind="api",
                active=True,
            )
        else:
            source = upsert_source(
                db,
                domain=spec.domain,
                name=spec.name,
                kind="rss" if spec.kind == "rss" else "api",
                feed_url=spec.feed_url,
                country_iso2=spec.country_iso2,
            )
        recent = db.execute(
            select(Article.id, Article.title, Article.description)
            .where(
                Article.source_id == source.id,
                Article.fetched_at >= cutoff,
                Article.is_duplicate_of.is_(None),
            )
            .order_by(Article.fetched_at.desc())
            .limit(400)
        ).all()
        corpus = [
            (item_id, f"{title or ''} {description or ''}")
            for item_id, title, description in recent
        ]
        duplicate_of = find_near_duplicate(f"{row['title']} {row.get('description') or ''}", corpus)
        article = Article(
            source_id=source.id,
            url=row["url"],
            url_hash=row["url_hash"],
            title=row["title"],
            author=row.get("author"),
            description=row.get("description"),
            content_text=row.get("content_text"),
            image_url=row.get("image_url"),
            language=row.get("language") or "en",
            published_at=row.get("published_at"),
            fetched_at=_now(),
            processing_status="done" if duplicate_of else "pending",
            processed_at=_now() if duplicate_of else None,
            is_duplicate_of=duplicate_of,
        )
        db.add(article)
        db.flush()
        existing.add(row["url_hash"])
        if duplicate_of:
            duplicates += 1
        else:
            inserted += 1
    return fetched, inserted, duplicates


def ingest_all(db: Session, *, pause_seconds: float = 0.4) -> list[IngestionRun]:
    """Fetch every active configured source and write an ingestion run for each.

    One failing source does not stop the others. API keys that are missing
    are recorded as a failed run and logged.
    """
    session = build_session()
    runs: list[IngestionRun] = []
    try:
        for spec in FETCH_SOURCES:
            run = IngestionRun(
                started_at=_now(),
                source_id=None,
                fetched=0,
                inserted=0,
                duplicates=0,
                errors=0,
                status="running",
            )
            db.add(run)
            db.flush()
            logger.info("ingest start source=%s", spec.domain)
            try:
                if spec.kind == "rss" or spec.provider in {"guardian", "newsapi", "gnews"}:
                    source = upsert_source(
                        db,
                        domain=spec.domain,
                        name=spec.name,
                        kind="rss" if spec.kind == "rss" else "api",
                        feed_url=spec.feed_url,
                        country_iso2=spec.country_iso2,
                    )
                    run.source_id = source.id
                raw = _fetch(spec, session)
                fetched, inserted, duplicates = _store_batch(db, spec, raw)
                run.fetched = fetched
                run.inserted = inserted
                run.duplicates = duplicates
                run.status = "success"
            except MissingAPIKey as exc:
                logger.info("skip %s: %s", spec.domain, exc)
                run.errors = 1
                run.status = "failed"
            except Exception:
                logger.exception("ingest failed source=%s", spec.domain)
                run.errors = 1
                run.status = "failed"
            finally:
                run.finished_at = _now()
                db.commit()
                runs.append(run)
                if pause_seconds:
                    time.sleep(pause_seconds)
    finally:
        session.close()
    logger.info("ingest finished runs=%s", len(runs))
    return runs
