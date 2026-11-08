"""NLP helpers that do not download Transformer weights."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.nlp.classify import keyword_category
from app.nlp.countries import detect_countries
from app.nlp.credibility import level_for, score_credibility
from app.nlp.events import ClusterItem, cluster_items
from app.nlp.keywords import extract_keywords
from app.nlp.pipeline import analyse
from app.nlp.summarize import summarize_text
from app.nlp.trending import KeywordArticle, build_topics, trend_math
from app.services.query import page_count


def test_country_aliases_and_codes():
    found = dict(detect_countries("Talks in the U.S. and Beijing. The Kremlin denied it. Pakistani officials attended."))
    assert found["US"] >= 1
    assert found["CN"] >= 1
    assert found["RU"] >= 1
    assert found["PK"] >= 1
    assert detect_countries("A meeting was held on Monday.") == []


def test_short_summary_is_unchanged():
    text = "Pakistan and India agreed to talk next month."
    assert summarize_text(text) == text


def test_keyword_category_and_terms():
    label, confidence = keyword_category("Parliament opened the election campaign before the vote")
    assert label == "politics"
    assert 0 < confidence <= 1
    keywords = extract_keywords(
        "Border talks between Pakistan and India resumed after the ceasefire",
        ["United Nations"],
    )
    assert keywords
    assert "United Nations" in keywords


def test_credibility_factors_and_levels():
    calm = score_credibility(
        source_reliability=90,
        independent_sources=4,
        has_author=True,
        has_date=True,
        has_url=True,
        named_orgs=2,
        title="Diplomats meet in Geneva",
        sentiment_label="neutral",
        sentiment_score=0.6,
    )
    loud = score_credibility(
        source_reliability=30,
        independent_sources=1,
        has_author=False,
        has_date=False,
        has_url=True,
        named_orgs=0,
        title="SHOCKING CHAOS!!! Leader DESTROYED",
        sentiment_label="negative",
        sentiment_score=0.97,
    )
    assert calm.level == "high"
    assert calm.score >= 70
    assert len(calm.factors) == 5
    assert abs(sum(item["weight"] for item in calm.factors) - 1) < 1e-9
    assert loud.score < calm.score
    assert level_for(39) == "low"
    assert level_for(40) == "medium"
    assert level_for(70) == "high"


def test_trend_math_and_topics():
    score, growth = trend_math(6, 2)
    assert growth == 200
    assert score > 0
    assert trend_math(3, 3)[0] == 0
    now = datetime(2026, 11, 3, tzinfo=timezone.utc)
    rows = []
    for index in range(3):
        rows.append(
            KeywordArticle(
                article_id=index + 1,
                source_id=index % 2 + 1,
                published_at=now - timedelta(hours=2),
                keywords=["border talks", "pakistan"],
            )
        )
    rows.append(
        KeywordArticle(
            article_id=9,
            source_id=1,
            published_at=now - timedelta(days=2),
            keywords=["border talks"],
        )
    )
    topics = build_topics(
        rows,
        now=now,
        window=timedelta(hours=24),
        country_names={"pakistan", "india"},
    )
    assert topics
    assert topics[0].article_count >= 3
    assert any("border talks" in topic.keywords for topic in topics)


def test_cluster_groups_similar_headlines():
    now = datetime(2026, 11, 3, tzinfo=timezone.utc)
    groups = cluster_items(
        [
            ClusterItem(1, "Pakistan and India resume border talks", "Pakistan and India resume border talks in Lahore after the ceasefire", now),
            ClusterItem(2, "Pakistan and India resume border talks in Lahore", "Pakistan and India resume border talks in Lahore following the ceasefire", now),
            ClusterItem(3, "Central bank raises interest rates", "The central bank raises interest rates to fight inflation", now),
        ]
    )
    assert len(groups) == 1
    assert set(groups[0].member_ids) == {1, 2}


def test_analyse_uses_injected_models():
    result = analyse(
        title="Talks in Islamabad and New Delhi",
        description="Pakistani and Indian diplomats met.",
        content_text="Officials discussed a treaty.",
        author="A Reporter",
        published_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
        url="https://example.com/a",
        source_reliability=80,
        summarize_fn=lambda text: "Pakistan and India discussed a treaty.",
        classify_fn=lambda title, text: ("international_relations", 0.81),
        sentiment_fn=lambda text: ("neutral", 0.66),
        ner_fn=lambda text: [("United Nations", "ORG", 1), ("Islamabad", "LOC", 2)],
    )
    assert result.summary.startswith("Pakistan")
    assert result.category == "international_relations"
    assert result.sentiment_label == "neutral"
    assert result.countries[0][0] in {"PK", "IN"}
    assert result.credibility_score is not None
    assert result.keywords


def test_page_count():
    assert page_count(240, 20) == 12
    assert page_count(0, 20) == 0
