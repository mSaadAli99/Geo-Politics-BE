"""Shared query parameters and the admin-key check."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException, Query

from app.core.config import settings
from app.services.filters import ArticleQuery, DateWindow, EventQuery, TimelineQuery

CategoryName = Literal[
    "politics",
    "economy",
    "conflict",
    "international_relations",
    "global_affairs",
]
SentimentName = Literal["positive", "negative", "neutral"]


def _window(
    from_dt: datetime | None,
    to_dt: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    if from_dt and to_dt and from_dt > to_dt:
        raise HTTPException(status_code=422, detail="'from' must be before 'to'")
    return from_dt, to_dt


def article_filters(
    q: str | None = Query(None),
    category: CategoryName | None = Query(None),
    country: str | None = Query(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    sentiment: SentimentName | None = Query(None),
    source_id: int | None = Query(None, ge=1),
    topic_id: int | None = Query(None, ge=1),
    event_id: int | None = Query(None, ge=1),
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    min_credibility: float | None = Query(None, ge=0, le=100),
    sort: Literal["latest", "relevance", "credibility"] = Query("latest"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ArticleQuery:
    """Validate article list parameters. ``sort=relevance`` requires ``q``."""
    start, end = _window(from_dt, to_dt)
    text = q.strip() if q else None
    if sort == "relevance" and not text:
        raise HTTPException(status_code=422, detail="sort=relevance requires q")
    return ArticleQuery(
        q=text or None,
        category=category,
        country=country.upper() if country else None,
        sentiment=sentiment,
        source_id=source_id,
        topic_id=topic_id,
        event_id=event_id,
        from_dt=start,
        to_dt=end,
        min_credibility=min_credibility,
        sort=sort,
        page=page,
        page_size=page_size,
    )


def date_category_filters(
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    category: CategoryName | None = Query(None),
    country: str | None = Query(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
) -> DateWindow:
    start, end = _window(from_dt, to_dt)
    return DateWindow(
        from_dt=start,
        to_dt=end,
        category=category,
        country=country.upper() if country else None,
    )


def stats_filters(
    group_by: Literal["day", "category", "country", "source"] = Query("day"),
    q: str | None = Query(None),
    category: CategoryName | None = Query(None),
    country: str | None = Query(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
) -> tuple[str, DateWindow]:
    start, end = _window(from_dt, to_dt)
    window = DateWindow(
        from_dt=start,
        to_dt=end,
        category=category,
        country=country.upper() if country else None,
        q=q.strip() if q else None,
    )
    return group_by, window


def event_filters(
    q: str | None = Query(None),
    category: CategoryName | None = Query(None),
    country: str | None = Query(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    min_sources: int = Query(2, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> EventQuery:
    start, end = _window(from_dt, to_dt)
    return EventQuery(
        q=q.strip() if q else None,
        category=category,
        country=country.upper() if country else None,
        from_dt=start,
        to_dt=end,
        min_sources=min_sources,
        page=page,
        page_size=page_size,
    )


def timeline_filters(
    q: str | None = Query(None),
    topic_id: int | None = Query(None, ge=1),
    country: str | None = Query(None, min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    event_id: int | None = Query(None, ge=1),
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    granularity: Literal["day", "week"] = Query("day"),
) -> TimelineQuery:
    """At least one of q, topic_id, country, or event_id is required."""
    start, end = _window(from_dt, to_dt)
    text = q.strip() if q else None
    if not text and topic_id is None and country is None and event_id is None:
        raise HTTPException(
            status_code=422,
            detail="Provide q, topic_id, country, or event_id",
        )
    return TimelineQuery(
        q=text or None,
        topic_id=topic_id,
        country=country.upper() if country else None,
        event_id=event_id,
        from_dt=start,
        to_dt=end,
        granularity=granularity,
    )


def require_admin(
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    """Reject requests that do not send the configured admin key."""
    expected = settings.admin_api_key or ""
    provided = x_admin_key or ""
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing admin key")


ArticleFilters = Annotated[ArticleQuery, Depends(article_filters)]
WindowFilters = Annotated[DateWindow, Depends(date_category_filters)]
EventFilters = Annotated[EventQuery, Depends(event_filters)]
TimelineFilters = Annotated[TimelineQuery, Depends(timeline_filters)]
