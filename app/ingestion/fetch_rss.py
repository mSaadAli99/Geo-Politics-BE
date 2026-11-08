"""RSS fetch and parse. Network access stays in ``fetch_feed``."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import requests

from app.ingestion.http import TIMEOUT_SECONDS
from app.ingestion.types import RawArticle

logger = logging.getLogger(__name__)


def _published(entry: dict) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _image(entry: dict) -> str | None:
    thumbs = entry.get("media_thumbnail") or []
    if thumbs and thumbs[0].get("url"):
        return thumbs[0]["url"]
    media = entry.get("media_content") or []
    if media and media[0].get("url"):
        return media[0]["url"]
    for link in entry.get("links") or []:
        if str(link.get("type", "")).startswith("image") and link.get("href"):
            return link["href"]
    return None


def _entry_author(entry: dict) -> str | None:
    """Prefer a human name from common RSS/Atom author fields."""
    detail = entry.get("author_detail") or {}
    if isinstance(detail, dict) and detail.get("name"):
        return str(detail["name"])
    authors = entry.get("authors") or []
    for item in authors:
        if isinstance(item, dict) and item.get("name"):
            return str(item["name"])
        if isinstance(item, str) and item.strip():
            return item
    author = entry.get("author") or entry.get("dc_creator")
    if author:
        return str(author)
    return None


def parse_feed(content: bytes | str, *, assume_relevant: bool = True) -> list[RawArticle]:
    """Turn an RSS/Atom document into raw articles. No network."""
    parsed = feedparser.parse(content)
    language = None
    feed = parsed.get("feed") or {}
    if feed.get("language"):
        language = str(feed["language"])
    articles: list[RawArticle] = []
    for entry in parsed.entries:
        url = entry.get("link") or ""
        title = entry.get("title") or ""
        if not url or not title:
            continue
        summary = entry.get("summary") or entry.get("description") or ""
        author = _entry_author(entry)
        tags = entry.get("tags") or []
        section = tags[0].get("term") if tags else None
        articles.append(
            RawArticle(
                url=url,
                title=title,
                author=author,
                description=summary,
                content_text=summary,
                image_url=_image(entry),
                language=language,
                published_at=_published(entry),
                section=section,
                assume_relevant=assume_relevant,
            )
        )
    if getattr(parsed, "bozo", False) and not articles:
        logger.warning("RSS parse failed: %s", getattr(parsed, "bozo_exception", "unknown"))
    return articles


def fetch_feed(url: str, session: requests.Session, *, assume_relevant: bool = True) -> list[RawArticle]:
    """Download one feed and parse it."""
    response = session.get(url, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return parse_feed(response.content, assume_relevant=assume_relevant)
