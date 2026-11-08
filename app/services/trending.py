"""Trending topic queries."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ArticleTopic, Topic


def list_trending(db: Session, *, window: str, limit: int) -> list[dict]:
    """Topics for the 24h or 7d window, highest trend score first."""
    target = 24 * 3600 if window == "24h" else 7 * 24 * 3600
    length = func.extract("epoch", Topic.window_end - Topic.window_start)
    topics = db.scalars(
        select(Topic)
        .where(func.abs(length - target) < 3600)
        .order_by(Topic.trend_score.desc(), Topic.article_count.desc(), Topic.id.desc())
        .limit(limit)
    ).all()
    if not topics:
        return []
    topic_ids = [topic.id for topic in topics]
    samples: dict[int, list[int]] = {topic_id: [] for topic_id in topic_ids}
    rows = db.execute(
        select(ArticleTopic.topic_id, ArticleTopic.article_id)
        .where(ArticleTopic.topic_id.in_(topic_ids))
        .order_by(ArticleTopic.article_id)
    ).all()
    for topic_id, article_id in rows:
        bucket = samples[topic_id]
        if len(bucket) < 5:
            bucket.append(article_id)
    return [
        {
            "id": topic.id,
            "label": topic.label,
            "keywords": list(topic.keywords or []),
            "article_count": topic.article_count,
            "trend_score": topic.trend_score,
            "growth_pct": topic.growth_pct,
            "sample_article_ids": samples.get(topic.id, []),
        }
        for topic in topics
    ]


def window_delta(window: str) -> timedelta:
    """Kept for callers that want the matching timedelta."""
    return timedelta(hours=24) if window == "24h" else timedelta(days=7)
