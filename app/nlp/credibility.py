"""Explainable 0–100 credibility score."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DISCLAIMER = "Indicator based on defined factors, not a fact-check."

_SHOCK = re.compile(
    r"\b(shocking|unbelievable|you won't believe|destroyed|slams|obliterates|"
    r"exposed|bombshell|chaos)\b",
    re.IGNORECASE,
)
_CAPS = re.compile(r"\b[A-Z]{4,}\b")


@dataclass
class CredibilityResult:
    score: int
    level: str
    factors: list[dict] = field(default_factory=list)


def level_for(score: int) -> str:
    """Map a 0–100 score onto high / medium / low."""
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def corroboration_value(independent_sources: int) -> int:
    """1 source -> 20, 2 -> 50, 3 -> 75, 4 or more -> 100."""
    count = max(int(independent_sources or 1), 1)
    if count == 1:
        return 20
    if count == 2:
        return 50
    if count == 3:
        return 75
    return 100


def _sensationalism(title: str) -> tuple[int, str]:
    value = 100
    notes: list[str] = []
    caps = _CAPS.findall(title or "")
    if len(caps) >= 2:
        value -= 20
        notes.append("several all-caps words")
    if (title or "").count("!") >= 2:
        value -= 25
        notes.append("repeated exclamation marks")
    shocks = _SHOCK.findall(title or "")
    if shocks:
        value -= min(40, 15 * len(shocks))
        notes.append("clickbait wording")
    value = max(0, value)
    if not notes:
        return value, "No clickbait pattern detected in the headline."
    return value, "Penalty for " + ", ".join(notes) + "."


def _tone_value(label: str | None, score: float | None, independent_sources: int) -> tuple[int, str]:
    extreme = (
        label in {"positive", "negative"}
        and score is not None
        and score >= 0.9
        and independent_sources < 2
    )
    if extreme:
        return (
            40,
            "Sentiment confidence is very high and no second outlet has corroborated the story.",
        )
    return 100, "Tone is not extremely one-sided, or the story is corroborated."


def score_credibility(
    *,
    source_reliability: float,
    independent_sources: int,
    has_author: bool,
    has_date: bool,
    has_url: bool,
    named_orgs: int,
    title: str,
    sentiment_label: str | None,
    sentiment_score: float | None,
) -> CredibilityResult:
    """Combine the five weighted factors into a 0–100 score.

    Each factor is itself a 0–100 value. Weights sum to 1.
    """
    reliability = max(0, min(100, int(round(source_reliability))))
    corroboration = corroboration_value(independent_sources)
    attribution = 0
    bits: list[str] = []
    if has_author:
        attribution += 30
        bits.append("author")
    if has_date:
        attribution += 25
        bits.append("publish date")
    if has_url:
        attribution += 25
        bits.append("original link")
    if named_orgs > 0:
        attribution += 20
        bits.append("named organisation")
    if bits:
        attribution_note = "Present: " + ", ".join(bits) + "."
    else:
        attribution_note = "No author, date, link, or named organisation was found."
    sensationalism, sensationalism_note = _sensationalism(title or "")
    tone, tone_note = _tone_value(sentiment_label, sentiment_score, independent_sources)
    factors = [
        {
            "name": "Source reliability",
            "value": reliability,
            "weight": 0.4,
            "explanation": f"Outlet reliability score is {reliability}.",
        },
        {
            "name": "Corroboration",
            "value": corroboration,
            "weight": 0.25,
            "explanation": (
                f"{max(independent_sources, 1)} independent source"
                f"{'' if max(independent_sources, 1) == 1 else 's'} in this story."
            ),
        },
        {
            "name": "Attribution & transparency",
            "value": attribution,
            "weight": 0.15,
            "explanation": attribution_note,
        },
        {
            "name": "Headline sensationalism",
            "value": sensationalism,
            "weight": 0.1,
            "explanation": sensationalism_note,
        },
        {
            "name": "Tone extremity",
            "value": tone,
            "weight": 0.1,
            "explanation": tone_note,
        },
    ]
    raw = sum(item["value"] * item["weight"] for item in factors)
    score = int(round(max(0.0, min(100.0, raw))))
    return CredibilityResult(score=score, level=level_for(score), factors=factors)
