"""Article list and detail payloads."""

from __future__ import annotations

from app.schemas.common import (
    APIModel,
    CountryBrief,
    CredibilityBrief,
    CredibilityDetail,
    SentimentOut,
    SourceBrief,
    UTCDateTime,
)


class TopicBrief(APIModel):
    id: int
    label: str


class ArticleCard(APIModel):
    id: int
    title: str
    url: str
    source: SourceBrief
    author: str | None = None
    published_at: UTCDateTime | None = None
    image_url: str | None = None
    snippet: str | None = None
    summary: str | None = None
    category: str | None = None
    sentiment: SentimentOut | None = None
    credibility: CredibilityBrief | None = None
    countries: list[CountryBrief] = []
    event_id: int | None = None


class ArticleEntities(APIModel):
    persons: list[str] = []
    organizations: list[str] = []
    locations: list[str] = []


class ArticleDetail(ArticleCard):
    content_text: str | None = None
    entities: ArticleEntities | None = None
    keywords: list[str] | None = None
    topics: list[TopicBrief] | None = None
    credibility: CredibilityDetail | CredibilityBrief | None = None
    related_articles: list[ArticleCard] = []


class ArticlePage(APIModel):
    items: list[ArticleCard]
    total: int
    page: int
    page_size: int
    pages: int
