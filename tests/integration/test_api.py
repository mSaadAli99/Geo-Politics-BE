"""API contract tests against PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.ingestion.run import ingest_all
from app.ingestion.types import RawArticle
from app.models import Article, Country, Source
from app.nlp.pipeline import Analysis, process_article
from app.scheduler.jobs import cluster_recent, recompute_trending

pytestmark = pytest.mark.integration


def _country(db, iso2, iso3, name):
    db.add(Country(iso2=iso2, iso3=iso3, name=name, lat=30.0, lng=70.0, region="Asia"))
    db.flush()


def _source(db, name="BBC News", domain="bbc.co.uk"):
    source = Source(
        name=name,
        domain=domain,
        type="rss",
        feed_url="https://example.test/rss",
        reliability_tier="high",
        reliability_score=90,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(source)
    db.flush()
    return source


def _article(db, source, **overrides):
    now = datetime.now(timezone.utc)
    payload = dict(
        source_id=source.id,
        url="https://example.test/one",
        url_hash="hash-one",
        title="Pakistan and India hold border talks",
        author="Reporter",
        description="Diplomats met to discuss a treaty and the border.",
        content_text="Diplomats met to discuss a treaty and the border.",
        language="en",
        published_at=now - timedelta(hours=2),
        fetched_at=now,
        summary="Pakistan and India discussed the border.",
        category="international_relations",
        category_confidence=0.8,
        sentiment_label="neutral",
        sentiment_score=0.6,
        credibility_score=82,
        credibility_level="high",
        credibility_factors=[
            {
                "name": "Source reliability",
                "value": 90,
                "weight": 0.4,
                "explanation": "Test source.",
            }
        ],
        keywords=["border talks", "pakistan", "india"],
        processing_status="done",
        processed_at=now,
    )
    payload.update(overrides)
    article = Article(**payload)
    db.add(article)
    db.flush()
    return article


def test_health_categories_and_validation(client, db):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["db"] == "ok"
    assert body["pending_articles"] == 0
    categories = client.get("/api/v1/categories")
    assert categories.status_code == 200
    assert len(categories.json()) == 5
    bad = client.get("/api/v1/articles", params={"category": "sports"})
    assert bad.status_code == 422
    relevance = client.get("/api/v1/articles", params={"sort": "relevance"})
    assert relevance.status_code == 422
    timeline = client.get("/api/v1/timeline")
    assert timeline.status_code == 422
    missing = client.get("/api/v1/articles/9999")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Article not found"


def test_article_filters_search_and_duplicates(client, db):
    _country(db, "PK", "PAK", "Pakistan")
    _country(db, "IN", "IND", "India")
    source = _source(db)
    done = _article(db, source)
    pending = _article(
        db,
        source,
        url="https://example.test/pending",
        url_hash="hash-pending",
        title="Pending story about NATO",
        summary="should be hidden",
        category="politics",
        sentiment_label="negative",
        credibility_score=10,
        processing_status="pending",
        processed_at=None,
    )
    _article(
        db,
        source,
        url="https://example.test/dup",
        url_hash="hash-dup",
        title="Duplicate headline",
        is_duplicate_of=done.id,
    )
    from app.models import ArticleCountry

    db.add(ArticleCountry(article_id=done.id, country_iso2="PK", mentions=2, is_primary=True))
    db.add(ArticleCountry(article_id=done.id, country_iso2="IN", mentions=1, is_primary=False))
    db.commit()

    listed = client.get("/api/v1/articles")
    assert listed.status_code == 200
    payload = listed.json()
    ids = [item["id"] for item in payload["items"]]
    assert done.id in ids
    assert pending.id in ids
    assert all(item["title"] != "Duplicate headline" for item in payload["items"])
    pending_card = next(item for item in payload["items"] if item["id"] == pending.id)
    assert pending_card["summary"] is None
    assert pending_card["category"] is None
    assert pending_card["sentiment"] is None

    found = client.get("/api/v1/articles", params={"q": "border", "sort": "relevance"})
    assert found.status_code == 200
    assert any(item["id"] == done.id for item in found.json()["items"])
    by_country = client.get("/api/v1/articles", params={"country": "PK"})
    assert [item["id"] for item in by_country.json()["items"]] == [done.id]

    detail = client.get(f"/api/v1/articles/{done.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["credibility"]["disclaimer"].startswith("Indicator based on")
    assert body["countries"][0]["iso2"] == "PK"
    assert body["keywords"]


def test_admin_key_and_ingest_shape(client, db, monkeypatch):
    denied = client.post("/api/v1/admin/ingest")
    assert denied.status_code == 401
    monkeypatch.setattr("app.api.v1.admin._run_ingest", lambda run_id: None)
    accepted = client.post("/api/v1/admin/ingest", headers={"X-Admin-Key": "change-me"})
    assert accepted.status_code == 202
    assert "run_id" in accepted.json()
    missing = client.post("/api/v1/admin/reprocess/5", headers={"X-Admin-Key": "change-me"})
    assert missing.status_code == 404


def test_ingest_process_cluster_and_trending(client, db, monkeypatch):
    _country(db, "PK", "PAK", "Pakistan")
    _country(db, "IN", "IND", "India")
    db.commit()

    def fake_fetch(spec, session):
        if spec.domain != "bbc.co.uk":
            return []
        return [
            RawArticle(
                url="https://bbc.example/one",
                title="Pakistan and India resume border talks in Lahore",
                description="Diplomats from Pakistan and India met after the ceasefire.",
                content_text="Diplomats from Pakistan and India met in Lahore after the ceasefire to discuss a treaty.",
                language="en",
                published_at=datetime.now(timezone.utc) - timedelta(hours=3),
                assume_relevant=True,
            ),
            RawArticle(
                url="https://bbc.example/two",
                title="Pakistan and India resume border talks in Lahore today",
                description="Diplomats from Pakistan and India met after the ceasefire today.",
                content_text="Diplomats from Pakistan and India met in Lahore after the ceasefire today to discuss a treaty.",
                language="en",
                published_at=datetime.now(timezone.utc) - timedelta(hours=1),
                assume_relevant=True,
            ),
        ]

    monkeypatch.setattr("app.ingestion.run._fetch", fake_fetch)
    monkeypatch.setattr("app.ingestion.run.time.sleep", lambda *_: None)
    runs = ingest_all(db, pause_seconds=0)
    assert any(run.inserted for run in runs)
    articles = db.scalars(select(Article).where(Article.is_duplicate_of.is_(None))).all()
    assert len(articles) >= 1

    def fake_analyse(**kwargs):
        return Analysis(
            summary="Pakistan and India resumed border talks.",
            category="international_relations",
            category_confidence=0.9,
            sentiment_label="neutral",
            sentiment_score=0.7,
            entities=[("United Nations", "ORG", 1)],
            countries=[("PK", 2, True), ("IN", 1, False)],
            keywords=["border talks", "pakistan", "india"],
            credibility_score=75,
            credibility_level="high",
            credibility_factors=[
                {
                    "name": "Source reliability",
                    "value": 90,
                    "weight": 0.4,
                    "explanation": "Test.",
                }
            ],
        )

    monkeypatch.setattr("app.nlp.pipeline.analyse", fake_analyse)
    for article in articles:
        process_article(db, article)
    db.commit()

    # Two near-duplicate headlines from the same source: one may be marked duplicate.
    # Add a second outlet so clustering has two sources when both survived.
    other = _source(db, name="Second Desk", domain="second.example")
    kept = db.scalars(select(Article).where(Article.is_duplicate_of.is_(None))).all()
    if len(kept) == 1:
        clone = _article(
            db,
            other,
            url="https://dawn.example/one",
            url_hash="dawn-one",
            title="Pakistan and India resume border talks in Lahore",
            description="Dawn: diplomats from Pakistan and India met after the ceasefire.",
            keywords=["border talks", "pakistan", "india"],
        )
        from app.models import ArticleCountry

        db.add(ArticleCountry(article_id=clone.id, country_iso2="PK", mentions=1, is_primary=True))
        db.commit()
    cluster_recent(db)
    recompute_trending(db)

    overview = client.get("/api/v1/stats/overview")
    assert overview.status_code == 200
    assert overview.json()["total_articles"] >= 1
    countries = client.get("/api/v1/countries")
    assert countries.status_code == 200
    assert any(item["iso2"] == "PK" for item in countries.json())
    detail = client.get("/api/v1/countries/PK")
    assert detail.status_code == 200
    assert detail.json()["country"]["name"] == "Pakistan"
    events = client.get("/api/v1/events", params={"min_sources": 1})
    assert events.status_code == 200
    trending = client.get("/api/v1/trending", params={"window": "24h"})
    assert trending.status_code == 200
    timeline = client.get("/api/v1/timeline", params={"country": "PK"})
    assert timeline.status_code == 200
    assert "buckets" in timeline.json()
    sources = client.get("/api/v1/sources")
    assert sources.status_code == 200
    assert any(item["domain"] == "bbc.co.uk" for item in sources.json())
