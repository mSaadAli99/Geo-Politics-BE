"""Health, categories, and sources."""

from __future__ import annotations

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from app.ingestion.sources_config import AGGREGATOR_DOMAINS
from app.models import Article, IngestionRun, Source
from app.nlp.classify import CATEGORIES, CATEGORY_LABELS


def health(db: Session) -> dict:
    """Database ping plus the latest ingest time and the pending queue."""
    try:
        db.execute(text("SELECT 1"))
        db_state = "ok"
        status = "ok"
    except Exception:
        return {
            "status": "degraded",
            "db": "error",
            "last_ingest_at": None,
            "pending_articles": 0,
        }
    last_ingest = db.scalar(select(func.max(IngestionRun.finished_at)))
    pending = db.scalar(
        select(func.count(Article.id)).where(
            Article.processing_status == "pending",
            Article.is_duplicate_of.is_(None),
        )
    )
    return {
        "status": status,
        "db": db_state,
        "last_ingest_at": last_ingest,
        "pending_articles": int(pending or 0),
    }


def list_categories(db: Session) -> list[dict]:
    """Every category, including ones that currently have zero articles."""
    rows = db.execute(
        select(Article.category, func.count(Article.id))
        .where(Article.is_duplicate_of.is_(None), Article.category.is_not(None))
        .group_by(Article.category)
    ).all()
    counts = {category: int(count) for category, count in rows}
    return [
        {"key": key, "label": CATEGORY_LABELS[key], "count": counts.get(key, 0)}
        for key in CATEGORIES
    ]


def list_sources(db: Session) -> list[dict]:
    """Outlets with a feed, plus any outlet that already has articles.

    Aggregator hosts (NewsAPI, GNews) are hidden. Articles are attributed to
    the outlet that published them.
    """
    article_count = func.count(Article.id)
    rows = db.execute(
        select(Source, article_count)
        .outerjoin(
            Article,
            and_(Article.source_id == Source.id, Article.is_duplicate_of.is_(None)),
        )
        .where(Source.domain.notin_(AGGREGATOR_DOMAINS))
        .group_by(Source.id)
        .having(
            or_(
                article_count > 0,
                and_(Source.is_active.is_(True), Source.feed_url.is_not(None)),
            )
        )
        .order_by(Source.name)
    ).all()
    return [
        {
            "id": source.id,
            "name": source.name,
            "domain": source.domain,
            "reliability_tier": source.reliability_tier,
            "reliability_score": source.reliability_score,
            "article_count": int(count or 0),
        }
        for source, count in rows
    ]
