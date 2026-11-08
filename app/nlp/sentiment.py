"""Sentiment on the headline plus the summary."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_LABELS = {
    "negative": "negative",
    "neutral": "neutral",
    "positive": "positive",
    "label_0": "negative",
    "label_1": "neutral",
    "label_2": "positive",
}


def sentiment_text(text: str | None, sentiment_pipeline=None) -> tuple[str | None, float | None]:
    """Return ``(label, score)`` using the configured 3-class model."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return None, None
    if sentiment_pipeline is None:
        from app.nlp.models import get_sentiment

        sentiment_pipeline = get_sentiment()
    result = sentiment_pipeline(cleaned[:2000])
    if not result:
        return None, None
    row = result[0]
    raw = str(row.get("label", "")).lower()
    label = _LABELS.get(raw)
    if label is None:
        logger.warning("unknown sentiment label %s", raw)
        return None, None
    score = row.get("score")
    return label, None if score is None else float(score)
