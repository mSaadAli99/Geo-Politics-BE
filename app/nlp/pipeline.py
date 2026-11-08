"""Run every NLP step for one article and persist the result.

Transformer models load only if a step is called without a fake. The API
requeues articles and leaves this module to the worker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.ingestion.clean import clean_author
from app.models import Article, ArticleCountry, ArticleEntity, Country, Entity
from app.nlp.classify import classify_text
from app.nlp.countries import country_meta, detect_countries
from app.nlp.credibility import score_credibility
from app.nlp.keywords import extract_keywords
from app.nlp.ner import extract_entities
from app.nlp.sentiment import sentiment_text
from app.nlp.summarize import summarize_text

logger = logging.getLogger(__name__)


@dataclass
class Analysis:
    """Fields produced for one article. Failed steps stay None."""

    summary: str | None = None
    category: str | None = None
    category_confidence: float | None = None
    sentiment_label: str | None = None
    sentiment_score: float | None = None
    entities: list[tuple[str, str, int]] = field(default_factory=list)
    countries: list[tuple[str, int, bool]] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    credibility_score: int | None = None
    credibility_level: str | None = None
    credibility_factors: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _step(name: str, errors: list[str], fn):
    try:
        return fn()
    except Exception:
        logger.exception("nlp step failed: %s", name)
        errors.append(name)
        return None


def analyse(
    *,
    title: str,
    description: str | None,
    content_text: str | None,
    author: str | None,
    published_at: datetime | None,
    url: str | None,
    source_reliability: float,
    independent_sources: int = 1,
    summarize_fn=None,
    classify_fn=None,
    sentiment_fn=None,
    ner_fn=None,
) -> Analysis:
    """Run the article pipeline. One failed step does not stop the rest."""
    # Resolve callables at runtime so drain scripts can monkeypatch modules.
    summarize_fn = summarize_fn or summarize_text
    classify_fn = classify_fn or classify_text
    sentiment_fn = sentiment_fn or sentiment_text
    ner_fn = ner_fn or extract_entities
    result = Analysis()
    body = content_text or description or title
    summary = _step("summarise", result.errors, lambda: summarize_fn(body))
    if isinstance(summary, str):
        result.summary = summary
    classified = _step("classify", result.errors, lambda: classify_fn(title, body))
    if isinstance(classified, tuple) and classified[0]:
        result.category, result.category_confidence = classified
    sentiment_input = " ".join(part for part in (title, result.summary or description) if part)
    sentiment = _step("sentiment", result.errors, lambda: sentiment_fn(sentiment_input))
    if isinstance(sentiment, tuple) and sentiment[0]:
        result.sentiment_label, result.sentiment_score = sentiment
    ner_input = " ".join(
        part for part in (title, result.summary, (content_text or "")[:1200]) if part
    )
    entities = _step("ner", result.errors, lambda: ner_fn(ner_input))
    if isinstance(entities, list):
        result.entities = [(text, kind, mentions) for text, kind, mentions in entities[:40]]
    locations = [text for text, kind, _ in result.entities if kind == "LOC"]
    country_text = " ".join(
        part for part in (title, result.summary, description, (content_text or "")[:1200]) if part
    )
    try:
        ranked = detect_countries(country_text, locations)
        result.countries = [(code, mentions, index == 0) for index, (code, mentions) in enumerate(ranked)]
    except Exception:
        logger.exception("nlp step failed: countries")
        result.errors.append("countries")
    try:
        names = [text for text, _, _ in result.entities]
        result.keywords = extract_keywords(f"{title} {result.summary or body or ''}", names)
    except Exception:
        logger.exception("nlp step failed: keywords")
        result.errors.append("keywords")
    try:
        orgs = sum(1 for _, kind, _ in result.entities if kind == "ORG")
        scored = score_credibility(
            source_reliability=source_reliability,
            independent_sources=independent_sources,
            has_author=bool(clean_author(author)),
            has_date=published_at is not None,
            has_url=bool(url),
            named_orgs=orgs,
            title=title or "",
            sentiment_label=result.sentiment_label,
            sentiment_score=result.sentiment_score,
        )
        result.credibility_score = scored.score
        result.credibility_level = scored.level
        result.credibility_factors = scored.factors
    except Exception:
        logger.exception("nlp step failed: credibility")
        result.errors.append("credibility")
    return result


def _ensure_country(db: Session, iso2: str) -> Country | None:
    row = db.get(Country, iso2)
    if row is not None:
        return row
    meta = country_meta(iso2)
    if meta is None or not meta.get("name") or not meta.get("iso3"):
        return None
    row = Country(
        iso2=meta["iso2"],
        iso3=meta["iso3"],
        name=meta["name"],
        lat=meta.get("lat"),
        lng=meta.get("lng"),
        region=meta.get("region"),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        row = db.get(Country, iso2)
    return row


def _ensure_entity(db: Session, text: str, kind: str) -> Entity | None:
    if kind not in {"PER", "ORG", "LOC", "MISC"}:
        return None
    normalized = " ".join(text.lower().split())[:512]
    if not normalized:
        return None
    existing = db.scalar(
        select(Entity).where(Entity.normalized_text == normalized, Entity.type == kind)
    )
    if existing is not None:
        return existing
    row = Entity(text=text[:512], normalized_text=normalized, type=kind)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        row = db.scalar(
            select(Entity).where(Entity.normalized_text == normalized, Entity.type == kind)
        )
    return row


def apply_analysis(db: Session, article: Article, analysis: Analysis) -> None:
    """Write analysis fields and replace country/entity links."""
    article.summary = analysis.summary
    article.category = analysis.category
    article.category_confidence = analysis.category_confidence
    article.sentiment_label = analysis.sentiment_label
    article.sentiment_score = analysis.sentiment_score
    article.credibility_score = analysis.credibility_score
    article.credibility_level = analysis.credibility_level
    article.credibility_factors = analysis.credibility_factors or None
    article.keywords = analysis.keywords or None
    db.execute(delete(ArticleCountry).where(ArticleCountry.article_id == article.id))
    db.execute(delete(ArticleEntity).where(ArticleEntity.article_id == article.id))
    db.flush()
    seen_countries: set[str] = set()
    for iso2, mentions, primary in analysis.countries:
        code = (iso2 or "").upper()
        if not code or code in seen_countries:
            continue
        country = _ensure_country(db, code)
        if country is None:
            continue
        seen_countries.add(country.iso2)
        db.add(
            ArticleCountry(
                article_id=article.id,
                country_iso2=country.iso2,
                mentions=mentions,
                is_primary=primary and len(seen_countries) == 1,
            )
        )
    seen_entities: set[int] = set()
    for text, kind, mentions in analysis.entities:
        entity = _ensure_entity(db, text, kind)
        if entity is None or entity.id in seen_entities:
            continue
        seen_entities.add(entity.id)
        db.add(ArticleEntity(article_id=article.id, entity_id=entity.id, mentions=mentions))


def process_article(db: Session, article: Article) -> Analysis:
    """Analyse one article and mark it done."""
    reliability = 50
    if article.source is not None:
        reliability = article.source.reliability_score
    independent = 1
    if article.event_id:
        independent = (
            db.scalar(
                select(func.count(func.distinct(Article.source_id))).where(
                    Article.event_id == article.event_id,
                    Article.is_duplicate_of.is_(None),
                )
            )
            or 1
        )
    analysis = analyse(
        title=article.title,
        description=article.description,
        content_text=article.content_text,
        author=article.author,
        published_at=article.published_at,
        url=article.url,
        source_reliability=reliability,
        independent_sources=int(independent),
    )
    apply_analysis(db, article, analysis)
    article.processing_status = "done"
    article.processing_error = "; ".join(analysis.errors) or None
    article.processed_at = datetime.now(timezone.utc)
    return analysis


def rescore_article(db: Session, article: Article) -> None:
    """Recompute credibility after clustering changes the source count."""
    if article.source is None:
        db.refresh(article, attribute_names=["source"])
    reliability = article.source.reliability_score if article.source is not None else 50
    independent = 1
    if article.event_id:
        independent = (
            db.scalar(
                select(func.count(func.distinct(Article.source_id))).where(
                    Article.event_id == article.event_id,
                    Article.is_duplicate_of.is_(None),
                )
            )
            or 1
        )
    orgs = (
        db.scalar(
            select(func.count())
            .select_from(ArticleEntity)
            .join(Entity, Entity.id == ArticleEntity.entity_id)
            .where(ArticleEntity.article_id == article.id, Entity.type == "ORG")
        )
        or 0
    )
    scored = score_credibility(
        source_reliability=reliability,
        independent_sources=int(independent),
        has_author=bool(clean_author(article.author)),
        has_date=article.published_at is not None,
        has_url=bool(article.url),
        named_orgs=int(orgs),
        title=article.title or "",
        sentiment_label=article.sentiment_label,
        sentiment_score=article.sentiment_score,
    )
    article.credibility_score = scored.score
    article.credibility_level = scored.level
    article.credibility_factors = scored.factors


def process_pending(db: Session, batch_size: int) -> int:
    """Claim a batch of pending articles and analyse them.

    Rows left in ``processing`` by a crashed worker are returned to ``pending``
    first. This assumes a single worker, which is how the scheduler is run.

    Hugging Face inference can take minutes (especially on first model load).
    Neon closes idle transactions, so we snapshot each article, commit, run
    NLP with no open transaction, then write results in a short commit.
    """
    if batch_size <= 0:
        return 0
    stuck = db.scalars(select(Article).where(Article.processing_status == "processing")).all()
    for article in stuck:
        article.processing_status = "pending"
    if stuck:
        db.commit()
    ids = list(
        db.scalars(
            select(Article.id)
            .where(Article.processing_status == "pending", Article.is_duplicate_of.is_(None))
            .order_by(Article.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()
    )
    if not ids:
        return 0
    db.execute(update(Article).where(Article.id.in_(ids)).values(processing_status="processing"))
    db.commit()

    snapshots: list[dict] = []
    claimed = db.scalars(
        select(Article).where(Article.id.in_(ids)).options(selectinload(Article.source))
    ).all()
    for article in claimed:
        reliability = article.source.reliability_score if article.source is not None else 50
        independent = 1
        if article.event_id:
            independent = (
                db.scalar(
                    select(func.count(func.distinct(Article.source_id))).where(
                        Article.event_id == article.event_id,
                        Article.is_duplicate_of.is_(None),
                    )
                )
                or 1
            )
        snapshots.append(
            {
                "id": article.id,
                "title": article.title,
                "description": article.description,
                "content_text": article.content_text,
                "author": article.author,
                "published_at": article.published_at,
                "url": article.url,
                "source_reliability": reliability,
                "independent_sources": int(independent),
            }
        )
    db.commit()

    done = 0
    for snap in snapshots:
        article_id = snap["id"]
        try:
            analysis = analyse(
                title=snap["title"],
                description=snap["description"],
                content_text=snap["content_text"],
                author=snap["author"],
                published_at=snap["published_at"],
                url=snap["url"],
                source_reliability=snap["source_reliability"],
                independent_sources=snap["independent_sources"],
            )
            article = db.get(Article, article_id)
            if article is None:
                continue
            apply_analysis(db, article, analysis)
            article.processing_status = "done"
            article.processing_error = "; ".join(analysis.errors) or None
            article.processed_at = datetime.now(timezone.utc)
            db.commit()
            done += 1
        except Exception:
            logger.exception("pipeline crashed article=%s", article_id)
            db.rollback()
            failed = db.get(Article, article_id)
            if failed is not None:
                failed.processing_status = "failed"
                failed.processing_error = "pipeline crashed"
                failed.processed_at = datetime.now(timezone.utc)
                db.commit()
    return done
