"""Cleaning, URL canonicalisation, and near-duplicate checks."""

from __future__ import annotations

from datetime import datetime, timezone

from app.ingestion.clean import (
    clean_articles,
    clean_author,
    is_english,
    is_geopolitical,
    strip_html,
)
from app.ingestion.dedupe import canonicalize_url, find_near_duplicate, hash_url
from app.ingestion.fetch_rss import parse_feed
from app.ingestion.types import RawArticle

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>Pakistan and India hold border talks</title>
  <link>https://example.com/story?utm_source=rss&amp;id=1#top</link>
  <description>&lt;p&gt;Diplomats met in Islamabad.&lt;/p&gt;</description>
  <pubDate>Mon, 02 Nov 2026 10:15:00 GMT</pubDate>
</item>
<item>
  <title>City win the premier league</title>
  <link>https://example.com/sport</link>
  <description>A football match decided the title.</description>
</item>
</channel></rss>
"""


def test_canonicalize_and_hash_drop_tracking():
    left = canonicalize_url("https://Example.com/a/?utm_source=x&id=2#frag")
    right = canonicalize_url("https://example.com/a?id=2")
    assert left == right
    assert hash_url("https://Example.com/a/?utm_source=x&id=2#frag") == hash_url(
        "https://example.com/a?id=2"
    )


def test_strip_html_and_english_and_relevance():
    assert strip_html("<p>Hello&nbsp;world</p>") == "Hello world"
    assert is_english("The minister said the talks would continue in the capital today", None)
    assert not is_english("Le ministre a declare que les discussions continuaient aujourd hui", "fr")
    assert is_geopolitical("Border talks", "diplomats met", "world", assume_relevant=False, country_hit=True)
    assert not is_geopolitical(
        "Premier league final",
        "football fans celebrated",
        "sport",
        assume_relevant=True,
        country_hit=True,
    )


def test_clean_author_drops_placeholders():
    assert clean_author("none@none.com (AFP)") == "AFP"
    assert clean_author("none@none.com (Reuters)") == "Reuters"
    assert clean_author("editorial@africanews.com (Alexis Caraco)") == "Alexis Caraco"
    assert clean_author("newsroom@example.com") is None
    assert clean_author("none") is None
    assert clean_author("Ada Lovelace") == "Ada Lovelace"


def test_clean_keeps_geo_and_drops_sport():
    items = parse_feed(RSS, assume_relevant=False)
    assert len(items) == 2
    frame = clean_articles(items)
    assert len(frame) == 1
    assert "utm_source" not in frame.iloc[0]["url_hash"]
    assert frame.iloc[0]["title"].startswith("Pakistan")


def test_near_duplicate_same_wording():
    corpus = [(4, "Pakistan and India resume border talks in Lahore after the ceasefire")]
    found = find_near_duplicate(
        "Pakistan and India resume border talks in Lahore after the ceasefire",
        corpus,
    )
    assert found == 4
    assert (
        find_near_duplicate(
            "Central bank raises interest rates to fight inflation across the region",
            corpus,
        )
        is None
    )


def test_parse_feed_date_is_utc():
    item = parse_feed(RSS)[0]
    assert item.published_at == datetime(2026, 11, 2, 10, 15, tzinfo=timezone.utc)
    assert isinstance(item, RawArticle)
