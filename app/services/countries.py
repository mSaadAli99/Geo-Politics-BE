"""Country map and country detail queries."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Article, ArticleCountry, ArticleTopic, Country, Topic
from app.services.filters import DateWindow
from app.services.serialize import article_card

_LABELS = ("positive", "negative", "neutral")


def _article_conds(window: DateWindow) -> list:
    conds = [Article.is_duplicate_of.is_(None)]
    if window.category:
        conds.append(Article.category == window.category)
    if window.country:
        conds.append(ArticleCountry.country_iso2 == window.country)
    if window.from_dt:
        conds.append(Article.published_at >= window.from_dt)
    if window.to_dt:
        conds.append(Article.published_at <= window.to_dt)
    return conds


def _dominant(bucket: dict) -> str | None:
    if bucket["positive"] == bucket["negative"] == bucket["neutral"] == 0:
        return None
    return max(_LABELS, key=lambda label: bucket[label])


def _average(bucket: dict) -> float | None:
    labeled = bucket["positive"] + bucket["negative"] + bucket["neutral"]
    if not labeled:
        return None
    return round((bucket["positive"] - bucket["negative"]) / labeled, 4)


def _percentages(bucket: dict) -> dict[str, int]:
    """Turn labeled counts into integers that sum to 100 (or all zeros)."""
    labeled = bucket["positive"] + bucket["negative"] + bucket["neutral"]
    if not labeled:
        return {"positive": 0, "negative": 0, "neutral": 0}
    raw = {
        label: (bucket[label] * 100.0) / labeled
        for label in _LABELS
    }
    floors = {label: int(value) for label, value in raw.items()}
    remainder = 100 - sum(floors.values())
    order = sorted(_LABELS, key=lambda label: (raw[label] - floors[label]), reverse=True)
    for label in order[:remainder]:
        floors[label] += 1
    return floors


def list_countries(db: Session, window: DateWindow) -> list[dict]:
    """Countries with at least one matching article, for the map."""
    rows = db.execute(
        select(Country, Article.sentiment_label, func.count(Article.id))
        .join(ArticleCountry, ArticleCountry.country_iso2 == Country.iso2)
        .join(Article, Article.id == ArticleCountry.article_id)
        .where(*_article_conds(window))
        .group_by(Country.iso2, Article.sentiment_label)
    ).all()
    by_iso: dict[str, dict] = {}
    for country, label, count in rows:
        slot = by_iso.setdefault(country.iso2, {"country": country, "counts": {}})
        slot["counts"][label] = int(count)
    items = []
    for iso2, slot in by_iso.items():
        country = slot["country"]
        bucket = {"positive": 0, "negative": 0, "neutral": 0, "total": 0}
        for label, count in slot["counts"].items():
            bucket["total"] += count
            if label in ("positive", "negative", "neutral"):
                bucket[label] += count
        if bucket["total"] < 1:
            continue
        items.append(
            {
                "iso2": country.iso2,
                "iso3": country.iso3,
                "name": country.name,
                "lat": country.lat,
                "lng": country.lng,
                "article_count": bucket["total"],
                "avg_sentiment": _average(bucket),
                "dominant_sentiment": _dominant(bucket),
            }
        )
    items.sort(key=lambda item: (-item["article_count"], item["name"]))
    return items


def get_country(db: Session, iso2: str, window: DateWindow) -> dict | None:
    """One country, its breakdown, and the ten latest articles."""
    country = db.get(Country, iso2.upper())
    if country is None:
        return None
    scoped = DateWindow(
        from_dt=window.from_dt,
        to_dt=window.to_dt,
        category=window.category,
        country=country.iso2,
    )
    conds = _article_conds(scoped)
    sentiment_rows = db.execute(
        select(Article.sentiment_label, func.count(Article.id))
        .join(ArticleCountry, ArticleCountry.article_id == Article.id)
        .where(*conds)
        .group_by(Article.sentiment_label)
    ).all()
    bucket = {"positive": 0, "negative": 0, "neutral": 0, "total": 0}
    for label, count in sentiment_rows:
        amount = int(count)
        bucket["total"] += amount
        if label in ("positive", "negative", "neutral"):
            bucket[label] += amount
    breakdown = _percentages(bucket)
    categories = db.execute(
        select(Article.category, func.count(Article.id))
        .join(ArticleCountry, ArticleCountry.article_id == Article.id)
        .where(*conds, Article.category.is_not(None))
        .group_by(Article.category)
        .order_by(func.count(Article.id).desc())
        .limit(5)
    ).all()
    topics = db.execute(
        select(Topic.id, Topic.label, func.count(func.distinct(Article.id)))
        .join(ArticleTopic, ArticleTopic.topic_id == Topic.id)
        .join(Article, Article.id == ArticleTopic.article_id)
        .join(ArticleCountry, ArticleCountry.article_id == Article.id)
        .where(*conds)
        .group_by(Topic.id)
        .order_by(func.count(func.distinct(Article.id)).desc())
        .limit(5)
    ).all()
    latest = db.scalars(
        select(Article)
        .join(ArticleCountry, ArticleCountry.article_id == Article.id)
        .where(*conds)
        .options(
            selectinload(Article.source),
            selectinload(Article.country_links).selectinload(ArticleCountry.country),
        )
        .order_by(Article.published_at.desc().nulls_last())
        .limit(10)
    ).unique().all()
    return {
        "country": {
            "iso2": country.iso2,
            "iso3": country.iso3,
            "name": country.name,
            "lat": country.lat,
            "lng": country.lng,
            "region": country.region,
        },
        "article_count": bucket["total"],
        "dominant_sentiment": _dominant(bucket),
        "sentiment_breakdown": breakdown,
        "top_categories": [{"category": category, "count": int(count)} for category, count in categories],
        "top_topics": [
            {"id": topic_id, "label": label, "article_count": int(count)}
            for topic_id, label, count in topics
        ],
        "latest_articles": [article_card(article) for article in latest],
    }
