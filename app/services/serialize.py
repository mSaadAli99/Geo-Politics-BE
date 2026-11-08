"""Turn ORM rows into the API contract."""

from __future__ import annotations

from app.ingestion.clean import clean_author
from app.models import Article
from app.schemas.article import ArticleCard, ArticleDetail, ArticleEntities, TopicBrief
from app.schemas.common import (
    DISCLAIMER,
    CountryBrief,
    CredibilityBrief,
    CredibilityDetail,
    CredibilityFactor,
    SentimentOut,
    SourceBrief,
)


def snippet_for(article: Article) -> str | None:
    """First ~200 characters of the summary, otherwise the description."""
    if article.processing_status == "done" and article.summary:
        text = article.summary
    else:
        text = article.description or article.content_text or ""
    text = " ".join(text.split())
    if not text:
        return None
    return text[:200]


def _countries(article: Article) -> list[CountryBrief]:
    links = sorted(
        article.country_links,
        key=lambda link: (not link.is_primary, -link.mentions, link.country_iso2),
    )
    items: list[CountryBrief] = []
    for link in links:
        if link.country is None:
            continue
        items.append(CountryBrief(iso2=link.country.iso2, name=link.country.name))
    return items


def article_card(article: Article) -> ArticleCard:
    """List card. AI fields are null until processing_status is done."""
    done = article.processing_status == "done"
    sentiment = None
    credibility = None
    if done and article.sentiment_label:
        sentiment = SentimentOut(
            label=article.sentiment_label,
            score=round(float(article.sentiment_score or 0), 4),
        )
    if done and article.credibility_score is not None and article.credibility_level:
        credibility = CredibilityBrief(
            score=int(round(article.credibility_score)),
            level=article.credibility_level,
        )
    return ArticleCard(
        id=article.id,
        title=article.title,
        url=article.url,
        source=SourceBrief(
            id=article.source.id,
            name=article.source.name,
            domain=article.source.domain,
            reliability_tier=article.source.reliability_tier,
        ),
        author=clean_author(article.author),
        published_at=article.published_at,
        image_url=article.image_url,
        snippet=snippet_for(article),
        summary=article.summary if done else None,
        category=article.category if done else None,
        sentiment=sentiment,
        credibility=credibility,
        countries=_countries(article) if done else [],
        event_id=article.event_id,
    )


def _entities(article: Article) -> ArticleEntities:
    persons: list[str] = []
    organizations: list[str] = []
    locations: list[str] = []
    links = sorted(article.entity_links, key=lambda link: (-link.mentions, link.entity_id))
    for link in links:
        if link.entity is None:
            continue
        bucket = {"PER": persons, "ORG": organizations, "LOC": locations}.get(link.entity.type)
        if bucket is not None and link.entity.text not in bucket:
            bucket.append(link.entity.text)
    return ArticleEntities(persons=persons, organizations=organizations, locations=locations)


def _credibility_detail(article: Article) -> CredibilityDetail | None:
    if article.credibility_score is None or not article.credibility_level:
        return None
    factors = []
    for item in article.credibility_factors or []:
        factors.append(CredibilityFactor.model_validate(item))
    return CredibilityDetail(
        score=int(round(article.credibility_score)),
        level=article.credibility_level,
        factors=factors,
        disclaimer=DISCLAIMER,
    )


def article_detail(article: Article, related: list[Article]) -> ArticleDetail:
    """Full article. AI sections stay null while analysis is still running."""
    card = article_card(article)
    payload = card.model_dump()
    payload["content_text"] = article.content_text
    payload["related_articles"] = [article_card(item) for item in related]
    if article.processing_status != "done":
        payload["entities"] = None
        payload["keywords"] = None
        payload["topics"] = None
        payload["credibility"] = None
        return ArticleDetail(**payload)
    topics = []
    for link in article.topic_links:
        if link.topic is not None:
            topics.append(TopicBrief(id=link.topic.id, label=link.topic.label))
    payload["entities"] = _entities(article)
    payload["keywords"] = list(article.keywords or [])
    payload["topics"] = topics
    payload["credibility"] = _credibility_detail(article)
    return ArticleDetail(**payload)
