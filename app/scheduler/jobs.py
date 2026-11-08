"""Scheduled work: ingest, NLP, clustering, and trending topics."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import setup_logging
from app.ingestion.run import ingest_all
from app.models import Article, ArticleEntity, ArticleTopic, Country, Event, Topic
from app.nlp.events import ClusterItem, cluster_items
from app.nlp.pipeline import process_pending, rescore_article
from app.nlp.trending import KeywordArticle, build_topics

logger = logging.getLogger(__name__)


def _session() -> Session:
    return SessionLocal()


def ingest_job() -> None:
    """Fetch every configured source."""
    setup_logging()
    logger.info("ingest_job started")
    db = _session()
    try:
        ingest_all(db)
    except Exception:
        logger.exception("ingest_job failed")
        db.rollback()
    finally:
        db.close()
    logger.info("ingest_job finished")


def process_job() -> None:
    """Drain pending articles in repeated batches until the queue is empty.

    Stops after a large cap so ingest/cluster/trending can still run, then the
    next scheduled process_job continues where this left off.
    """
    setup_logging()
    logger.info("process_job started")
    db = _session()
    try:
        total = 0
        # Keep working through the backlog instead of only one small batch.
        while total < 400:
            done = process_pending(db, max(settings.process_batch_size, 16))
            total += done
            logger.info("process_job batch analysed=%s total=%s", done, total)
            if done == 0:
                break
        logger.info("process_job analysed=%s", total)
    except Exception:
        logger.exception("process_job failed")
        db.rollback()
    finally:
        db.close()


def _refresh_event(db: Session, event: Event) -> None:
    members = db.scalars(
        select(Article)
        .where(Article.event_id == event.id, Article.is_duplicate_of.is_(None))
        .options(selectinload(Article.country_links))
    ).all()
    if not members:
        return
    event.article_count = len(members)
    event.source_count = len({article.source_id for article in members})
    times = [article.published_at or article.fetched_at for article in members]
    event.first_seen_at = min(times)
    event.last_seen_at = max(times)
    categories = [article.category for article in members if article.category]
    if categories:
        event.category = Counter(categories).most_common(1)[0][0]
    primaries = [
        link.country_iso2
        for article in members
        for link in article.country_links
        if link.is_primary
    ]
    if primaries:
        event.primary_country_iso2 = Counter(primaries).most_common(1)[0][0]
    representative = next((article for article in members if article.title == event.title), members[0])
    event.summary = representative.summary or representative.description


def cluster_recent(db: Session, *, hours: int = 72) -> int:
    """Cluster articles from the last ``hours`` into events and rescore them.

    Returns the number of multi-article clusters written.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    articles = db.scalars(
        select(Article)
        .where(
            Article.processing_status == "done",
            Article.is_duplicate_of.is_(None),
            Article.published_at.is_not(None),
            Article.published_at >= cutoff,
        )
        .options(
            selectinload(Article.entity_links).selectinload(ArticleEntity.entity),
            selectinload(Article.source),
            selectinload(Article.country_links),
        )
    ).all()
    by_id = {article.id: article for article in articles}
    items: list[ClusterItem] = []
    for article in articles:
        entity_text = " ".join(
            link.entity.text for link in article.entity_links if link.entity is not None
        )
        text = f"{article.title} {article.summary or article.description or ''} {entity_text}"
        items.append(
            ClusterItem(
                id=article.id,
                title=article.title,
                text=text,
                published_at=article.published_at,
            )
        )
    groups = cluster_items(items)
    grouped: set[int] = set()
    touched: set[int] = set()
    for group in groups:
        members = [by_id[item_id] for item_id in group.member_ids if item_id in by_id]
        if len(members) < 2:
            continue
        existing_ids = [member.event_id for member in members if member.event_id]
        event: Event | None = None
        if existing_ids:
            event = db.get(Event, Counter(existing_ids).most_common(1)[0][0])
        if event is None:
            event = Event(title=group.title)
            db.add(event)
            db.flush()
        event.title = group.title
        for member in members:
            member.event_id = event.id
            grouped.add(member.id)
        touched.add(event.id)
    for article in articles:
        if article.id not in grouped:
            article.event_id = None
    db.flush()
    for event_id in touched:
        event = db.get(Event, event_id)
        if event is not None:
            _refresh_event(db, event)
    db.flush()
    linked = select(Article.event_id).where(Article.event_id.is_not(None))
    empty_ids = db.scalars(select(Event.id).where(~Event.id.in_(linked))).all()
    if empty_ids:
        db.execute(delete(Event).where(Event.id.in_(list(empty_ids))))
    for article in articles:
        rescore_article(db, article)
    db.commit()
    return len(groups)


def cluster_job() -> None:
    """Group the last 72 hours of articles into events."""
    setup_logging()
    logger.info("cluster_job started")
    db = _session()
    try:
        count = cluster_recent(db)
        logger.info("cluster_job clusters=%s", count)
    except Exception:
        logger.exception("cluster_job failed")
        db.rollback()
    finally:
        db.close()


def recompute_trending(db: Session) -> int:
    """Replace trending topics for the 24h and 7d windows.

    Returns the number of topics stored.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    articles = db.scalars(
        select(Article)
        .where(
            Article.processing_status == "done",
            Article.is_duplicate_of.is_(None),
            Article.published_at.is_not(None),
            Article.published_at >= cutoff,
            Article.keywords.is_not(None),
        )
        .order_by(Article.published_at.desc())
        .limit(5000)
    ).all()
    rows: list[KeywordArticle] = []
    for article in articles:
        words = article.keywords if isinstance(article.keywords, list) else []
        if not words or article.published_at is None:
            continue
        rows.append(
            KeywordArticle(
                article_id=article.id,
                source_id=article.source_id,
                published_at=article.published_at,
                keywords=[str(word) for word in words],
            )
        )
    names = {name.lower() for name in db.scalars(select(Country.name)).all() if name}
    db.execute(delete(ArticleTopic))
    db.execute(delete(Topic))
    created = 0
    for window in (timedelta(hours=24), timedelta(days=7)):
        drafts = build_topics(rows, now=now, window=window, country_names=names)
        for draft in drafts[:25]:
            topic = Topic(
                label=draft.label,
                keywords=draft.keywords,
                window_start=draft.window_start,
                window_end=draft.window_end,
                article_count=draft.article_count,
                trend_score=draft.trend_score,
                growth_pct=draft.growth_pct,
                computed_at=now,
            )
            db.add(topic)
            db.flush()
            for article_id in draft.article_ids:
                db.add(ArticleTopic(article_id=article_id, topic_id=topic.id))
            created += 1
    db.commit()
    return created


def trending_job() -> None:
    """Recompute 24h and 7d trending topics."""
    setup_logging()
    logger.info("trending_job started")
    db = _session()
    try:
        count = recompute_trending(db)
        logger.info("trending_job topics=%s", count)
    except Exception:
        logger.exception("trending_job failed")
        db.rollback()
    finally:
        db.close()
