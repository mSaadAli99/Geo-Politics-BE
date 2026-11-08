"""Curated fetch targets. Reliability scores live in ``source_reliability.json``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import BASE_DIR

DATA_DIR = BASE_DIR / "app" / "data"


@dataclass(frozen=True)
class FetchSource:
    """One place the ingester knows how to pull from."""

    name: str
    domain: str
    kind: str
    feed_url: str | None = None
    country_iso2: str | None = None
    provider: str | None = None
    assume_relevant: bool = True


FETCH_SOURCES: tuple[FetchSource, ...] = (
    FetchSource(
        "BBC News",
        "bbc.co.uk",
        "rss",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "GB",
    ),
    FetchSource(
        "Al Jazeera",
        "aljazeera.com",
        "rss",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "QA",
        assume_relevant=False,
    ),
    FetchSource(
        "DW",
        "dw.com",
        "rss",
        "https://rss.dw.com/rdf/rss-en-world",
        "DE",
    ),
    FetchSource(
        "France 24",
        "france24.com",
        "rss",
        "https://www.france24.com/en/rss",
        "FR",
    ),
    FetchSource(
        "UN News",
        "news.un.org",
        "rss",
        "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
        None,
    ),
    FetchSource(
        "NPR",
        "npr.org",
        "rss",
        "https://feeds.npr.org/1004/rss.xml",
        "US",
    ),
    FetchSource(
        "The Guardian",
        "theguardian.com",
        "api",
        "https://content.guardianapis.com/search",
        "GB",
        provider="guardian",
    ),
    FetchSource(
        "Dawn",
        "dawn.com",
        "rss",
        "https://www.dawn.com/feeds/world",
        "PK",
    ),
    FetchSource(
        "The Hindu",
        "thehindu.com",
        "rss",
        "https://www.thehindu.com/news/international/feeder/default.rss",
        "IN",
    ),
    FetchSource(
        "CBC News",
        "cbc.ca",
        "rss",
        "https://rss.cbc.ca/lineup/world.xml",
        "CA",
    ),
    FetchSource(
        "The Diplomat",
        "thediplomat.com",
        "rss",
        "https://thediplomat.com/feed/",
        None,
    ),
    FetchSource(
        "Euronews",
        "euronews.com",
        "rss",
        "https://www.euronews.com/rss?level=theme&name=news",
        None,
        assume_relevant=False,
    ),
    FetchSource(
        "Africanews",
        "africanews.com",
        "rss",
        "https://www.africanews.com/feed/rss",
        None,
    ),
    FetchSource(
        "Sky News",
        "sky.com",
        "rss",
        "https://feeds.skynews.com/feeds/rss/world.xml",
        "GB",
    ),
    FetchSource(
        "NewsAPI",
        "newsapi.org",
        "api",
        None,
        None,
        provider="newsapi",
        assume_relevant=False,
    ),
    FetchSource(
        "GNews",
        "gnews.io",
        "api",
        None,
        None,
        provider="gnews",
        assume_relevant=False,
    ),
)

AGGREGATOR_DOMAINS = frozenset({"newsapi.org", "gnews.io"})


@lru_cache
def reliability_table() -> dict[str, dict]:
    """Load the hand-written source reliability table."""
    path = DATA_DIR / "source_reliability.json"
    return json.loads(path.read_text(encoding="utf-8"))


def reliability_for(domain: str) -> tuple[str, int]:
    """Return ``(tier, score)`` for a domain, or unknown/50."""
    item = reliability_table().get(domain.lower())
    if not item:
        return "unknown", 50
    return str(item.get("tier", "unknown")), int(item.get("score", 50))
