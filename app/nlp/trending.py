"""Trending-topic maths. Persistence lives in ``recompute_trending``."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class KeywordArticle:
    article_id: int
    source_id: int
    published_at: datetime
    keywords: list[str]


@dataclass
class TopicDraft:
    label: str
    keywords: list[str]
    article_ids: list[int]
    article_count: int
    trend_score: float
    growth_pct: float
    window_start: datetime
    window_end: datetime
    sample_article_ids: list[int] = field(default_factory=list)


def trend_math(count: int, previous: int) -> tuple[float, float]:
    """Return ``(trend_score, growth_pct)``.

    ``trend_score = count * log(1 + growth)`` where growth is clamped at zero
    inside the log so a falling topic does not produce a complex score.
    ``growth_pct`` can be negative. A previous count of zero uses a baseline of 1.
    """
    baseline = previous if previous > 0 else 1
    growth = (count - previous) / baseline
    score = count * math.log(1 + max(growth, 0.0))
    return score, growth * 100


def _tokens(phrase: str) -> set[str]:
    return {part for part in phrase.lower().split() if part}


def _overlaps(left: str, right: str) -> bool:
    a = left.lower().strip()
    b = right.lower().strip()
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.5


def _label(keywords: list[str], country_names: set[str]) -> str:
    blob = " ".join(keywords).lower()
    found: list[str] = []
    for name in sorted(country_names, key=len, reverse=True):
        if len(name) < 4:
            continue
        if name in blob and not any(name in earlier or earlier in name for earlier in found):
            found.append(name)
        if len(found) == 2:
            return f"{found[0].title()}–{found[1].title()} relations"
    return keywords[0].title()


def build_topics(
    rows: list[KeywordArticle],
    *,
    now: datetime,
    window: timedelta,
    country_names: set[str] | None = None,
    min_articles: int = 3,
    min_sources: int = 2,
) -> list[TopicDraft]:
    """Build topics for one window against the previous window of the same length."""
    names = {name.lower() for name in (country_names or set())}
    current_start = now - window
    previous_start = now - (window * 2)
    current_ids: dict[str, set[int]] = {}
    current_sources: dict[str, set[int]] = {}
    previous_ids: dict[str, set[int]] = {}
    for row in rows:
        if row.published_at is None:
            continue
        for raw in row.keywords:
            keyword = " ".join(str(raw).lower().split())
            if len(keyword) < 3:
                continue
            if current_start <= row.published_at <= now:
                current_ids.setdefault(keyword, set()).add(row.article_id)
                current_sources.setdefault(keyword, set()).add(row.source_id)
            elif previous_start <= row.published_at < current_start:
                previous_ids.setdefault(keyword, set()).add(row.article_id)

    candidates = [
        keyword
        for keyword, ids in current_ids.items()
        if len(ids) >= min_articles and len(current_sources.get(keyword, ())) >= min_sources
    ]
    candidates.sort(key=lambda keyword: (-len(current_ids[keyword]), keyword))
    parent = {keyword: keyword for keyword in candidates}

    def find(keyword: str) -> str:
        while parent[keyword] != keyword:
            parent[keyword] = parent[parent[keyword]]
            keyword = parent[keyword]
        return keyword

    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            if _overlaps(left, right):
                parent[find(right)] = find(left)

    groups: dict[str, list[str]] = {}
    for keyword in candidates:
        groups.setdefault(find(keyword), []).append(keyword)

    drafts: list[TopicDraft] = []
    for keywords in groups.values():
        keywords = sorted(keywords, key=lambda keyword: (-len(current_ids[keyword]), keyword))
        article_ids: set[int] = set()
        sources: set[int] = set()
        prev: set[int] = set()
        for keyword in keywords:
            article_ids |= current_ids.get(keyword, set())
            sources |= current_sources.get(keyword, set())
            prev |= previous_ids.get(keyword, set())
        if len(article_ids) < min_articles or len(sources) < min_sources:
            continue
        ordered_ids = sorted(article_ids)
        score, growth_pct = trend_math(len(ordered_ids), len(prev))
        kept = keywords[:6]
        drafts.append(
            TopicDraft(
                label=_label(kept, names),
                keywords=kept,
                article_ids=ordered_ids,
                article_count=len(ordered_ids),
                trend_score=round(score, 4),
                growth_pct=round(growth_pct, 2),
                window_start=current_start,
                window_end=now,
                sample_article_ids=ordered_ids[:5],
            )
        )
    drafts.sort(key=lambda draft: (-draft.trend_score, -draft.article_count, draft.label))
    return drafts
