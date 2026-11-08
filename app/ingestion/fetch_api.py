"""Clients for NewsAPI, GNews, and The Guardian Open Platform."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import requests

from app.core.config import settings
from app.ingestion.dedupe import domain_from_url
from app.ingestion.http import TIMEOUT_SECONDS
from app.ingestion.types import RawArticle

logger = logging.getLogger(__name__)

_CHARS = re.compile(r"\s*\[\+\d+ chars\]\s*$", re.IGNORECASE)

_NEWS_QUERY = 'diplomacy OR sanctions OR NATO OR "United Nations" OR ceasefire OR election OR invasion OR tariff OR embassy'


class MissingAPIKey(RuntimeError):
    """Raised when a provider is configured but its key is empty."""


def _parse_dt(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_content(value: str | None) -> str | None:
    if not value:
        return None
    return _CHARS.sub("", value).strip() or None


def parse_newsapi(payload: dict, *, assume_relevant: bool = False) -> list[RawArticle]:
    """Map a NewsAPI ``everything`` payload to raw articles."""
    if payload.get("status") not in (None, "ok"):
        message = payload.get("message") or payload.get("code") or "NewsAPI error"
        raise RuntimeError(str(message))
    articles: list[RawArticle] = []
    for item in payload.get("articles") or []:
        url = item.get("url") or ""
        title = item.get("title") or ""
        if not url or not title or title.strip() == "[Removed]":
            continue
        source = item.get("source") or {}
        articles.append(
            RawArticle(
                url=url,
                title=title,
                author=item.get("author"),
                description=item.get("description"),
                content_text=_clean_content(item.get("content")) or item.get("description"),
                image_url=item.get("urlToImage"),
                language="en",
                published_at=_parse_dt(item.get("publishedAt")),
                assume_relevant=assume_relevant,
                outlet_name=source.get("name"),
                outlet_domain=domain_from_url(url),
            )
        )
    return articles


def parse_gnews(payload: dict, *, assume_relevant: bool = False) -> list[RawArticle]:
    """Map a GNews search payload to raw articles."""
    if payload.get("errors"):
        raise RuntimeError(str(payload["errors"]))
    articles: list[RawArticle] = []
    for item in payload.get("articles") or []:
        url = item.get("url") or ""
        title = item.get("title") or ""
        if not url or not title:
            continue
        source = item.get("source") or {}
        articles.append(
            RawArticle(
                url=url,
                title=title,
                author=None,
                description=item.get("description"),
                content_text=_clean_content(item.get("content")) or item.get("description"),
                image_url=item.get("image"),
                language="en",
                published_at=_parse_dt(item.get("publishedAt")),
                assume_relevant=assume_relevant,
                outlet_name=source.get("name"),
                outlet_domain=domain_from_url(url) or domain_from_url(source.get("url") or ""),
            )
        )
    return articles


def parse_guardian(payload: dict, *, assume_relevant: bool = True) -> list[RawArticle]:
    """Map a Guardian search payload to raw articles.

    ``bodyText`` is capped later. We keep the portion the API returned so the
    summariser has something to work with, and the public API only shows a snippet.
    """
    response = payload.get("response") or {}
    if response.get("status") not in (None, "ok"):
        raise RuntimeError(str(response.get("message") or "Guardian API error"))
    articles: list[RawArticle] = []
    for item in response.get("results") or []:
        url = item.get("webUrl") or ""
        title = item.get("webTitle") or ""
        if not url or not title:
            continue
        fields = item.get("fields") or {}
        trail = fields.get("trailText")
        body = fields.get("bodyText")
        articles.append(
            RawArticle(
                url=url,
                title=title,
                author=fields.get("byline"),
                description=trail,
                content_text=body or trail,
                image_url=fields.get("thumbnail"),
                language="en",
                published_at=_parse_dt(item.get("webPublicationDate")),
                section=item.get("sectionName"),
                assume_relevant=assume_relevant,
                outlet_name="The Guardian",
                outlet_domain="theguardian.com",
            )
        )
    return articles


def fetch_provider(
    provider: str,
    session: requests.Session,
    *,
    assume_relevant: bool = False,
) -> list[RawArticle]:
    """Call one provider. Raises ``MissingAPIKey`` when the key is blank."""
    if provider == "newsapi":
        if not settings.newsapi_key:
            raise MissingAPIKey("NEWSAPI_KEY is not set")
        response = session.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": _NEWS_QUERY,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 50,
                "apiKey": settings.newsapi_key,
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return parse_newsapi(response.json(), assume_relevant=assume_relevant)
    if provider == "gnews":
        if not settings.gnews_api_key:
            raise MissingAPIKey("GNEWS_API_KEY is not set")
        response = session.get(
            "https://gnews.io/api/v4/search",
            params={
                "q": _NEWS_QUERY,
                "lang": "en",
                "max": 10,
                "apikey": settings.gnews_api_key,
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return parse_gnews(response.json(), assume_relevant=assume_relevant)
    if provider == "guardian":
        if not settings.guardian_api_key:
            raise MissingAPIKey("GUARDIAN_API_KEY is not set")
        response = session.get(
            "https://content.guardianapis.com/search",
            params={
                "section": "world",
                "order-by": "newest",
                "page-size": 40,
                "show-fields": "trailText,byline,thumbnail,bodyText",
                "api-key": settings.guardian_api_key,
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return parse_guardian(response.json(), assume_relevant=True)
    raise RuntimeError(f"Unknown provider: {provider}")
