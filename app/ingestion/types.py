"""One fetched story before it is cleaned and stored."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawArticle:
    """Fields we can usually get from an API or an RSS entry.

    ``content_text`` is whatever the source already returned (a description,
    a truncated API body, or a short RSS summary). This project does not
    scrape full article pages.
    """

    url: str
    title: str
    author: str | None = None
    description: str | None = None
    content_text: str | None = None
    image_url: str | None = None
    language: str | None = None
    published_at: datetime | None = None
    section: str | None = None
    assume_relevant: bool = False
    outlet_name: str | None = None
    outlet_domain: str | None = None
