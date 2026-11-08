"""Parsers for the news APIs. No network."""

from __future__ import annotations

import pytest

from app.ingestion.fetch_api import MissingAPIKey, fetch_provider, parse_gnews, parse_guardian, parse_newsapi
from app.nlp.ner import extract_entities
from app.nlp.sentiment import sentiment_text


def test_parse_newsapi_strips_truncated_marker():
    rows = parse_newsapi(
        {
            "status": "ok",
            "articles": [
                {
                    "title": "Border talks",
                    "url": "https://www.bbc.com/news/1",
                    "description": "Diplomats met",
                    "content": "Diplomats met [+240 chars]",
                    "publishedAt": "2026-11-02T10:15:00Z",
                    "author": "Ada",
                    "urlToImage": "https://img.example/1.jpg",
                    "source": {"name": "BBC News"},
                },
                {"title": "[Removed]", "url": "https://example.com/gone"},
            ],
        }
    )
    assert len(rows) == 1
    assert rows[0].outlet_domain == "bbc.com"
    assert rows[0].content_text == "Diplomats met"
    assert rows[0].published_at is not None
    assert rows[0].published_at.tzinfo is not None


def test_parse_guardian_and_gnews():
    guardian = parse_guardian(
        {
            "response": {
                "status": "ok",
                "results": [
                    {
                        "webTitle": "Summit",
                        "webUrl": "https://www.theguardian.com/world/summit",
                        "webPublicationDate": "2026-11-02T10:15:00Z",
                        "sectionName": "World news",
                        "fields": {
                            "trailText": "A short trail",
                            "byline": "Ada",
                            "bodyText": "Full available text",
                            "thumbnail": "https://img.example/g.jpg",
                        },
                    }
                ],
            }
        }
    )
    assert guardian[0].outlet_domain == "theguardian.com"
    assert guardian[0].content_text == "Full available text"
    gnews = parse_gnews(
        {
            "articles": [
                {
                    "title": "Tariffs",
                    "url": "https://www.reuters.com/world/tariffs",
                    "description": "Markets moved",
                    "content": "Markets moved",
                    "publishedAt": "2026-11-02T11:00:00Z",
                    "image": "https://img.example/r.jpg",
                    "source": {"name": "Reuters", "url": "https://www.reuters.com"},
                }
            ]
        }
    )
    assert gnews[0].outlet_domain == "reuters.com"


def test_provider_without_a_key_is_skipped():
    with pytest.raises(MissingAPIKey):
        fetch_provider("newsapi", session=None)


def test_sentiment_and_ner_accept_injected_pipelines():
    label, score = sentiment_text(
        "Talks went well",
        sentiment_pipeline=lambda text: [{"label": "positive", "score": 0.91}],
    )
    assert label == "positive"
    assert score == 0.91
    entities = extract_entities(
        "Ada spoke in Geneva",
        ner_pipeline=lambda text: [
            {"word": "Ada", "entity_group": "PER", "score": 0.99},
            {"word": "Geneva", "entity_group": "LOC", "score": 0.2},
        ],
    )
    assert entities == [("Ada", "PER", 1)]
