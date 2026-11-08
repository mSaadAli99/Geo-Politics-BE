"""Seed countries and the curated sources. Optional synthetic demo rows."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.ingestion.dedupe import hash_url  # noqa: E402
from app.ingestion.run import upsert_source  # noqa: E402
from app.ingestion.sources_config import DATA_DIR, FETCH_SOURCES  # noqa: E402
from app.models import Article, ArticleCountry, Country, Event, Source  # noqa: E402


def seed_countries(db) -> int:
    rows = json.loads((DATA_DIR / "country_centroids.json").read_text(encoding="utf-8"))
    count = 0
    for row in rows:
        country = db.get(Country, row["iso2"])
        if country is None:
            db.add(Country(**row))
            count += 1
        else:
            country.iso3 = row["iso3"]
            country.name = row["name"]
            country.lat = row["lat"]
            country.lng = row["lng"]
            country.region = row["region"]
    db.flush()
    return count


def seed_sources(db) -> int:
    count = 0
    for spec in FETCH_SOURCES:
        before = db.scalar(select(Source.id).where(Source.domain == spec.domain))
        upsert_source(
            db,
            domain=spec.domain,
            name=spec.name,
            kind="rss" if spec.kind == "rss" else "api",
            feed_url=spec.feed_url,
            country_iso2=spec.country_iso2,
            active=True,
        )
        if before is None:
            count += 1
    db.flush()
    return count


def seed_demo(db) -> None:
    """Insert a few original sample stories so the API is not empty offline.

    The source is named as synthetic. These are not scraped articles.
    """
    source = db.scalar(select(Source).where(Source.domain == "sample.geopolitics.test"))
    if source is None:
        source = Source(
            name="Sample Desk (synthetic)",
            domain="sample.geopolitics.test",
            type="rss",
            feed_url=None,
            country_iso2=None,
            reliability_tier="medium",
            reliability_score=60,
            is_active=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(source)
        db.flush()
    now = datetime.now(timezone.utc)
    event = Event(
        title="Sample: Pakistan and India schedule border talks",
        summary="A synthetic example used to exercise the compare view.",
        category="international_relations",
        first_seen_at=now - timedelta(hours=5),
        last_seen_at=now - timedelta(hours=1),
        article_count=2,
        source_count=1,
        primary_country_iso2="PK",
    )
    db.add(event)
    db.flush()
    samples = [
        {
            "title": "Sample: Pakistan and India schedule border talks",
            "url": "https://sample.geopolitics.test/border-talks",
            "summary": "Pakistan and India plan to reopen a border crossing.",
            "category": "international_relations",
            "sentiment": "neutral",
            "score": 0.62,
            "published": now - timedelta(hours=5),
            "countries": [("PK", 2, True), ("IN", 1, False)],
        },
        {
            "title": "Sample: officials confirm the border talks will proceed",
            "url": "https://sample.geopolitics.test/border-talks-confirm",
            "summary": "Officials said the Pakistan-India border talks remain on the calendar.",
            "category": "international_relations",
            "sentiment": "positive",
            "score": 0.55,
            "published": now - timedelta(hours=1),
            "countries": [("PK", 1, True), ("IN", 1, False)],
        },
        {
            "title": "Sample: inflation report raises tariff pressure",
            "url": "https://sample.geopolitics.test/tariff-pressure",
            "summary": "A synthetic economy brief about inflation and tariffs.",
            "category": "economy",
            "sentiment": "negative",
            "score": 0.71,
            "published": now - timedelta(hours=3),
            "countries": [("US", 1, True)],
        },
    ]
    for item in samples:
        if db.scalar(select(Article.id).where(Article.url == item["url"])):
            continue
        article = Article(
            source_id=source.id,
            url=item["url"],
            url_hash=hash_url(item["url"]),
            title=item["title"],
            author="Sample Desk",
            description=item["summary"],
            content_text=item["summary"],
            language="en",
            published_at=item["published"],
            fetched_at=now,
            summary=item["summary"],
            category=item["category"],
            category_confidence=0.8,
            sentiment_label=item["sentiment"],
            sentiment_score=item["score"],
            credibility_score=64,
            credibility_level="medium",
            credibility_factors=[
                {
                    "name": "Source reliability",
                    "value": 60,
                    "weight": 0.4,
                    "explanation": "Synthetic source used for local demos.",
                }
            ],
            keywords=["sample", item["category"].replace("_", " ")],
            event_id=event.id if "border" in item["url"] else None,
            processing_status="done",
            processed_at=now,
        )
        db.add(article)
        db.flush()
        for iso2, mentions, primary in item["countries"]:
            if db.get(Country, iso2) is None:
                continue
            db.add(
                ArticleCountry(
                    article_id=article.id,
                    country_iso2=iso2,
                    mentions=mentions,
                    is_primary=primary,
                )
            )
    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed countries and news sources")
    parser.add_argument(
        "--with-demo",
        action="store_true",
        help="Also insert clearly labelled synthetic articles",
    )
    args = parser.parse_args()
    setup_logging()
    db = SessionLocal()
    try:
        countries = seed_countries(db)
        sources = seed_sources(db)
        if args.with_demo:
            seed_demo(db)
        db.commit()
        print(f"countries inserted or refreshed, new rows touched: {countries}; new sources: {sources}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
