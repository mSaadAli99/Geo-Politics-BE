"""Filter objects passed from the routers into the services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ArticleQuery:
    q: str | None = None
    category: str | None = None
    country: str | None = None
    sentiment: str | None = None
    source_id: int | None = None
    topic_id: int | None = None
    event_id: int | None = None
    from_dt: datetime | None = None
    to_dt: datetime | None = None
    min_credibility: float | None = None
    sort: str = "latest"
    page: int = 1
    page_size: int = 20


@dataclass
class DateWindow:
    from_dt: datetime | None = None
    to_dt: datetime | None = None
    category: str | None = None
    country: str | None = None
    q: str | None = None


@dataclass
class EventQuery:
    q: str | None = None
    category: str | None = None
    country: str | None = None
    from_dt: datetime | None = None
    to_dt: datetime | None = None
    min_sources: int = 2
    page: int = 1
    page_size: int = 20


@dataclass
class TimelineQuery:
    q: str | None = None
    topic_id: int | None = None
    country: str | None = None
    event_id: int | None = None
    from_dt: datetime | None = None
    to_dt: datetime | None = None
    granularity: str = "day"
