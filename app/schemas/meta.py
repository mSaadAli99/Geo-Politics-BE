"""Country, category, source, trending, and stats payloads."""

from __future__ import annotations

from app.schemas.article import ArticleCard
from app.schemas.common import APIModel, UTCDateTime


class CategoryCount(APIModel):
    key: str
    label: str
    count: int


class SourceOut(APIModel):
    id: int
    name: str
    domain: str
    reliability_tier: str
    reliability_score: int
    article_count: int


class CountryMapItem(APIModel):
    iso2: str
    iso3: str
    name: str
    lat: float | None = None
    lng: float | None = None
    article_count: int
    avg_sentiment: float | None = None
    dominant_sentiment: str | None = None


class CountryInfo(APIModel):
    iso2: str
    iso3: str
    name: str
    lat: float | None = None
    lng: float | None = None
    region: str | None = None


class SentimentBreakdown(APIModel):
    positive: int = 0
    negative: int = 0
    neutral: int = 0


class CategoryStat(APIModel):
    category: str
    count: int


class TopicStat(APIModel):
    id: int
    label: str
    article_count: int


class CountryDetail(APIModel):
    country: CountryInfo
    article_count: int
    dominant_sentiment: str | None = None
    sentiment_breakdown: SentimentBreakdown
    top_categories: list[CategoryStat]
    top_topics: list[TopicStat]
    latest_articles: list[ArticleCard]


class TrendingTopic(APIModel):
    id: int
    label: str
    keywords: list[str]
    article_count: int
    trend_score: float
    growth_pct: float
    sample_article_ids: list[int]


class Overview(APIModel):
    total_articles: int
    articles_today: int
    sources_count: int
    countries_count: int
    last_updated_at: UTCDateTime | None = None
    by_category: dict[str, int]
    by_sentiment: dict[str, int]


class SentimentGroup(APIModel):
    key: str
    positive: int
    negative: int
    neutral: int
    total: int


class HealthStatus(APIModel):
    status: str
    db: str
    last_ingest_at: UTCDateTime | None = None
    pending_articles: int
