"""Dashboard aggregates."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Article, ArticleCountry, Source
from app.nlp.classify import CATEGORIES
from app.services.filters import DateWindow

_SENTIMENTS = ("positive", "negative", "neutral")


def _base_stmt(window: DateWindow):
    conds = [Article.is_duplicate_of.is_(None)]
    if window.category:
        conds.append(Article.category == window.category)
    if window.from_dt:
        conds.append(Article.published_at >= window.from_dt)
    if window.to_dt:
        conds.append(Article.published_at <= window.to_dt)
    if window.q:
        tsq = func.plainto_tsquery("english", window.q)
        conds.append(Article.search_vector.op("@@")(tsq))
    stmt = select(Article.id).where(*conds)
    if window.country:
        stmt = stmt.where(
            Article.id.in_(
                select(ArticleCountry.article_id).where(
                    ArticleCountry.country_iso2 == window.country
                )
            )
        )
    return stmt


def _empty_sentiment() -> dict[str, int]:
    return {label: 0 for label in _SENTIMENTS}


def overview(db: Session) -> dict:
    """Top-line counts for the dashboard."""
    visible = Article.is_duplicate_of.is_(None)
    total = int(db.scalar(select(func.count(Article.id)).where(visible)) or 0)
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today = int(
        db.scalar(
            select(func.count(Article.id)).where(visible, Article.published_at >= start)
        )
        or 0
    )
    sources = int(
        db.scalar(select(func.count(func.distinct(Article.source_id))).where(visible)) or 0
    )
    countries = int(
        db.scalar(
            select(func.count(func.distinct(ArticleCountry.country_iso2)))
            .join(Article, Article.id == ArticleCountry.article_id)
            .where(visible)
        )
        or 0
    )
    last_fetch = db.scalar(select(func.max(Article.fetched_at)).where(visible))
    last_done = db.scalar(select(func.max(Article.processed_at)).where(visible))
    candidates = [value for value in (last_fetch, last_done) if value is not None]
    by_category = {key: 0 for key in CATEGORIES}
    for category, count in db.execute(
        select(Article.category, func.count(Article.id))
        .where(visible, Article.category.is_not(None))
        .group_by(Article.category)
    ):
        if category in by_category:
            by_category[category] = int(count)
    by_sentiment = _empty_sentiment()
    for label, count in db.execute(
        select(Article.sentiment_label, func.count(Article.id))
        .where(visible, Article.sentiment_label.is_not(None))
        .group_by(Article.sentiment_label)
    ):
        if label in by_sentiment:
            by_sentiment[label] = int(count)
    return {
        "total_articles": total,
        "articles_today": today,
        "sources_count": sources,
        "countries_count": countries,
        "last_updated_at": max(candidates) if candidates else None,
        "by_category": by_category,
        "by_sentiment": by_sentiment,
    }


def sentiment_breakdown(db: Session, group_by: str, window: DateWindow) -> list[dict]:
    """Sentiment counts grouped by day, category, country, or source."""
    ids = _base_stmt(window)
    if group_by == "day":
        key = func.to_char(func.date_trunc("day", Article.published_at), "YYYY-MM-DD")
        stmt = (
            select(key, Article.sentiment_label, func.count(Article.id))
            .where(Article.id.in_(ids), Article.published_at.is_not(None))
            .group_by(key, Article.sentiment_label)
            .order_by(key)
        )
    elif group_by == "category":
        stmt = (
            select(Article.category, Article.sentiment_label, func.count(Article.id))
            .where(Article.id.in_(ids), Article.category.is_not(None))
            .group_by(Article.category, Article.sentiment_label)
            .order_by(Article.category)
        )
    elif group_by == "country":
        stmt = (
            select(ArticleCountry.country_iso2, Article.sentiment_label, func.count(Article.id))
            .join(ArticleCountry, ArticleCountry.article_id == Article.id)
            .where(Article.id.in_(ids))
            .group_by(ArticleCountry.country_iso2, Article.sentiment_label)
            .order_by(ArticleCountry.country_iso2)
        )
    else:
        stmt = (
            select(Source.name, Article.sentiment_label, func.count(Article.id))
            .join(Source, Source.id == Article.source_id)
            .where(Article.id.in_(ids))
            .group_by(Source.name, Article.sentiment_label)
            .order_by(Source.name)
        )
    grouped: dict[str, dict[str, int]] = {}
    for raw_key, label, count in db.execute(stmt):
        if raw_key is None:
            continue
        slot = grouped.setdefault(str(raw_key), _empty_sentiment())
        if label in slot:
            slot[label] += int(count)
    return [
        {
            "key": key,
            "positive": slot["positive"],
            "negative": slot["negative"],
            "neutral": slot["neutral"],
            "total": slot["positive"] + slot["negative"] + slot["neutral"],
        }
        for key, slot in grouped.items()
    ]


def category_counts(db: Session, window: DateWindow) -> list[dict]:
    """Article counts per category for the active filters."""
    ids = _base_stmt(window)
    rows = db.execute(
        select(Article.category, func.count(Article.id))
        .where(Article.id.in_(ids), Article.category.is_not(None))
        .group_by(Article.category)
        .order_by(func.count(Article.id).desc())
    ).all()
    return [{"category": category, "count": int(count)} for category, count in rows]
