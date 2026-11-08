"""Timeline buckets and story markers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Article, ArticleCountry, ArticleTopic, Event
from app.services.filters import TimelineQuery
from app.services.serialize import article_card

_ITEM_CAP = 200


def _filter_conds(filters: TimelineQuery) -> list:
    conds = [Article.is_duplicate_of.is_(None), Article.published_at.is_not(None)]
    if filters.from_dt:
        conds.append(Article.published_at >= filters.from_dt)
    if filters.to_dt:
        conds.append(Article.published_at <= filters.to_dt)
    if filters.q:
        tsq = func.plainto_tsquery("english", filters.q)
        conds.append(Article.search_vector.op("@@")(tsq))
    if filters.topic_id:
        conds.append(
            Article.id.in_(
                select(ArticleTopic.article_id).where(ArticleTopic.topic_id == filters.topic_id)
            )
        )
    if filters.country:
        conds.append(
            Article.id.in_(
                select(ArticleCountry.article_id).where(
                    ArticleCountry.country_iso2 == filters.country
                )
            )
        )
    if filters.event_id:
        conds.append(Article.event_id == filters.event_id)
    return conds


def build_timeline(db: Session, filters: TimelineQuery) -> dict:
    """Daily or weekly buckets, plus chronological story markers.

    Buckets use the same flat shape as ``/stats/sentiment``:
    ``{date, positive, negative, neutral, total}``.
    ``total`` counts every matching article (including unclassified sentiment).
    Markers are capped so an open-ended query cannot load the whole table.
    """
    conds = _filter_conds(filters)
    bucket = func.date_trunc(filters.granularity, Article.published_at)
    label = func.to_char(bucket, "YYYY-MM-DD")
    rows = db.execute(
        select(label, Article.sentiment_label, func.count(Article.id))
        .where(*conds)
        .group_by(label, Article.sentiment_label)
        .order_by(label)
    ).all()
    buckets: dict[str, dict] = {}
    for day, sentiment, count in rows:
        if day is None:
            continue
        slot = buckets.setdefault(
            str(day),
            {"date": str(day), "positive": 0, "negative": 0, "neutral": 0, "total": 0},
        )
        amount = int(count)
        slot["total"] += amount
        if sentiment in ("positive", "negative", "neutral"):
            slot[sentiment] += amount
    articles = db.scalars(
        select(Article)
        .where(*conds)
        .options(
            selectinload(Article.source),
            selectinload(Article.country_links).selectinload(ArticleCountry.country),
        )
        .order_by(Article.published_at.desc())
        .limit(_ITEM_CAP)
    ).unique().all()
    event_ids = {article.event_id for article in articles if article.event_id}
    events = {}
    if event_ids:
        events = {
            event.id: event
            for event in db.scalars(select(Event).where(Event.id.in_(event_ids))).all()
        }
    grouped: dict[tuple, list[Article]] = {}
    for article in sorted(articles, key=lambda item: (item.published_at, item.id)):
        key = ("event", article.event_id) if article.event_id else ("article", article.id)
        grouped.setdefault(key, []).append(article)
    items = []
    for group in grouped.values():
        first = group[0]
        event = events.get(first.event_id) if first.event_id else None
        items.append(
            {
                "date": first.published_at,
                "event_id": event.id if event else None,
                "title": event.title if event else first.title,
                "article_count": event.article_count if event else 1,
                "top_article": article_card(first),
            }
        )
    return {"buckets": list(buckets.values()), "items": items}
