"""Event list, event detail, and the compare-sources payload."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Article, ArticleCountry, Country, Event
from app.services.filters import EventQuery
from app.services.query import count_stmt, page_count
from app.services.serialize import article_card


def _countries_for(db: Session, event_ids: list[int]) -> dict[int, list[dict]]:
    if not event_ids:
        return {}
    rows = db.execute(
        select(Article.event_id, Country.iso2, Country.name, ArticleCountry.is_primary)
        .join(ArticleCountry, ArticleCountry.article_id == Article.id)
        .join(Country, Country.iso2 == ArticleCountry.country_iso2)
        .where(
            Article.event_id.in_(event_ids),
            Article.is_duplicate_of.is_(None),
        )
    ).all()
    found: dict[int, dict[str, dict]] = {}
    for event_id, iso2, name, primary in rows:
        bucket = found.setdefault(event_id, {})
        current = bucket.get(iso2)
        if current is None or primary:
            bucket[iso2] = {"iso2": iso2, "name": name, "primary": bool(primary)}
    return {
        event_id: sorted(items.values(), key=lambda item: (not item["primary"], item["name"]))
        for event_id, items in found.items()
    }


def list_events(db: Session, filters: EventQuery) -> dict:
    """Paginated events. ``min_sources`` defaults to 2."""
    conds = [Event.source_count >= filters.min_sources]
    if filters.category:
        conds.append(Event.category == filters.category)
    if filters.from_dt:
        conds.append(Event.last_seen_at >= filters.from_dt)
    if filters.to_dt:
        conds.append(Event.first_seen_at <= filters.to_dt)
    stmt = select(Event).where(*conds)
    if filters.q:
        blob = func.concat(Event.title, " ", func.coalesce(Event.summary, ""))
        tsq = func.plainto_tsquery("english", filters.q)
        stmt = stmt.where(func.to_tsvector("english", blob).op("@@")(tsq))
    if filters.country:
        linked = (
            select(Article.event_id)
            .join(ArticleCountry, ArticleCountry.article_id == Article.id)
            .where(
                ArticleCountry.country_iso2 == filters.country,
                Article.event_id.is_not(None),
                Article.is_duplicate_of.is_(None),
            )
        )
        stmt = stmt.where(
            or_(Event.primary_country_iso2 == filters.country, Event.id.in_(linked))
        )
    stmt = stmt.order_by(Event.last_seen_at.desc().nulls_last(), Event.id.desc())
    total = count_stmt(db, stmt)
    rows = db.scalars(
        stmt.offset((filters.page - 1) * filters.page_size).limit(filters.page_size)
    ).all()
    country_map = _countries_for(db, [row.id for row in rows])
    items = []
    for row in rows:
        countries = [
            {"iso2": item["iso2"], "name": item["name"]} for item in country_map.get(row.id, [])
        ]
        items.append(
            {
                "id": row.id,
                "title": row.title,
                "category": row.category,
                "first_seen_at": row.first_seen_at,
                "last_seen_at": row.last_seen_at,
                "article_count": row.article_count,
                "source_count": row.source_count,
                "countries": countries,
            }
        )
    return {
        "items": items,
        "total": total,
        "page": filters.page,
        "page_size": filters.page_size,
        "pages": page_count(total, filters.page_size),
    }


def get_event(db: Session, event_id: int) -> dict | None:
    """One event, its articles, and the compare-sources block."""
    event = db.get(Event, event_id)
    if event is None:
        return None
    articles = db.scalars(
        select(Article)
        .where(Article.event_id == event.id, Article.is_duplicate_of.is_(None))
        .options(
            selectinload(Article.source),
            selectinload(Article.country_links).selectinload(ArticleCountry.country),
        )
        .order_by(Article.published_at.asc().nulls_last(), Article.id.asc())
    ).unique().all()
    country_map = _countries_for(db, [event.id])
    countries = [
        {"iso2": item["iso2"], "name": item["name"]} for item in country_map.get(event.id, [])
    ]
    cards = []
    spread_labels: list[str] = []
    seen_labels: set[str] = set()
    scores: list[int] = []
    sources = []
    for article in articles:
        card = article_card(article).model_dump()
        card["headline_sentiment"] = article.sentiment_label
        cards.append(card)
        if article.sentiment_label and article.sentiment_label not in seen_labels:
            seen_labels.add(article.sentiment_label)
            spread_labels.append(article.sentiment_label)
        if article.credibility_score is not None:
            scores.append(int(round(article.credibility_score)))
        sources.append(
            {
                "id": article.source.id,
                "name": article.source.name,
                "domain": article.source.domain,
                "article_id": article.id,
                "published_at": article.published_at,
                "sentiment": article.sentiment_label,
            }
        )
    dated = [article for article in articles if article.published_at is not None]
    earliest = min((article.published_at for article in dated), default=None)
    return {
        "event": {
            "id": event.id,
            "title": event.title,
            "summary": event.summary,
            "category": event.category,
            "first_seen_at": event.first_seen_at,
            "last_seen_at": event.last_seen_at,
            "article_count": event.article_count,
            "source_count": event.source_count,
            "countries": countries,
        },
        "articles": cards,
        "comparison": {
            "sources": sources,
            "sentiment_spread": spread_labels,
            "earliest_report": earliest,
            "credibility_range": {
                "min": min(scores) if scores else None,
                "max": max(scores) if scores else None,
            },
        },
    }
