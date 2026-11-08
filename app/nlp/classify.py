"""Article category. The live path uses the trained scikit-learn model."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

from app.core.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

CATEGORIES: tuple[str, ...] = (
    "politics",
    "economy",
    "conflict",
    "international_relations",
    "global_affairs",
)

CATEGORY_LABELS: dict[str, str] = {
    "politics": "Politics",
    "economy": "Economy",
    "conflict": "Conflict",
    "international_relations": "International Relations",
    "global_affairs": "Global Affairs",
}

_RULES: dict[str, tuple[str, ...]] = {
    "conflict": (
        "airstrike",
        "missile",
        "ceasefire",
        "invasion",
        "shelling",
        "militant",
        "artillery",
        "troops",
        "killed",
    ),
    "economy": (
        "inflation",
        "gdp",
        "tariff",
        "recession",
        "imf",
        "markets",
        "oil price",
        "debt",
        "trade",
        "sanction",
    ),
    "international_relations": (
        "diplomat",
        "embassy",
        "treaty",
        "summit",
        "ambassador",
        "nato",
        "united nations",
        "bilateral",
    ),
    "politics": (
        "election",
        "parliament",
        "ballot",
        "president",
        "prime minister",
        "vote",
        "opposition",
        "campaign",
    ),
    "global_affairs": (
        "climate",
        "refugee",
        "humanitarian",
        "pandemic",
        "emissions",
        "global health",
        "disaster",
    ),
}


def keyword_category(text: str) -> tuple[str, float]:
    """Bootstrap classifier used only when the trained model file is missing."""
    blob = (text or "").lower()
    scores: dict[str, int] = {}
    for category, words in _RULES.items():
        scores[category] = sum(1 for word in words if re.search(rf"\b{re.escape(word)}\b", blob))
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    if total == 0:
        return "global_affairs", 0.34
    return best, round(scores[best] / total, 4)


@lru_cache
def load_classifier():
    """Load ``classifier.joblib`` once. Returns None when it has not been trained."""
    path = Path(settings.classifier_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    if not path.exists():
        logger.warning("classifier not found at %s; using keyword fallback", path)
        return None
    import joblib

    return joblib.load(path)


def classify_text(title: str | None, text: str | None, classifier=None) -> tuple[str | None, float | None]:
    """Return ``(category, confidence)`` for one article."""
    blob = " ".join(part for part in (title, text) if part).strip()
    if not blob:
        return None, None
    model = load_classifier() if classifier is None else classifier
    if model is None:
        label, confidence = keyword_category(blob)
        return label, confidence
    label = str(model.predict([blob])[0])
    if label not in CATEGORIES:
        logger.warning("classifier returned unexpected label %s", label)
        return None, None
    proba = model.predict_proba([blob])[0]
    classes = list(getattr(model, "classes_", []))
    if not classes and hasattr(model, "named_steps"):
        classes = list(model.named_steps["clf"].classes_)
    confidence = float(proba[classes.index(label)]) if label in classes else None
    return label, None if confidence is None else round(confidence, 4)
