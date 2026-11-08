"""Event, timeline, and admin payloads."""

from __future__ import annotations

from app.schemas.article import ArticleCard
from app.schemas.common import APIModel, CountryBrief, UTCDateTime


class EventCard(APIModel):
    id: int
    title: str
    category: str | None = None
    first_seen_at: UTCDateTime | None = None
    last_seen_at: UTCDateTime | None = None
    article_count: int
    source_count: int
    countries: list[CountryBrief] = []


class EventPage(APIModel):
    items: list[EventCard]
    total: int
    page: int
    page_size: int
    pages: int


class EventArticle(ArticleCard):
    headline_sentiment: str | None = None


class ComparisonSource(APIModel):
    id: int
    name: str
    domain: str
    article_id: int
    published_at: UTCDateTime | None = None
    sentiment: str | None = None


class CredibilityRange(APIModel):
    min: int | None = None
    max: int | None = None


class EventComparison(APIModel):
    sources: list[ComparisonSource]
    # Unique sentiment labels across linked articles, e.g. ["negative", "neutral"].
    sentiment_spread: list[str] = []
    # ISO timestamp of the earliest linked article.
    earliest_report: UTCDateTime | None = None
    credibility_range: CredibilityRange


class EventInfo(APIModel):
    id: int
    title: str
    summary: str | None = None
    category: str | None = None
    first_seen_at: UTCDateTime | None = None
    last_seen_at: UTCDateTime | None = None
    article_count: int
    source_count: int
    countries: list[CountryBrief] = []


class EventDetail(APIModel):
    event: EventInfo
    articles: list[EventArticle]
    comparison: EventComparison


class TimelineBucket(APIModel):
    """Same shape as stats sentiment rows, with ``date`` instead of ``key``."""

    date: str
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    total: int = 0


class TimelineItem(APIModel):
    date: UTCDateTime | None = None
    event_id: int | None = None
    title: str
    article_count: int
    top_article: ArticleCard


class TimelineOut(APIModel):
    buckets: list[TimelineBucket]
    items: list[TimelineItem]


class IngestAccepted(APIModel):
    run_id: int


class IngestionRunOut(APIModel):
    id: int
    started_at: UTCDateTime
    finished_at: UTCDateTime | None = None
    source_id: int | None = None
    fetched: int
    inserted: int
    duplicates: int
    errors: int
    status: str
