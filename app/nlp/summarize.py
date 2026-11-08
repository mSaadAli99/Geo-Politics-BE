"""Summarisation with BART-family (DistilBART) and T5.

Live path: try DistilBART first, then T5-small, then a short extractive lead
so articles are never left without a summary when models hiccup.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_MIN_WORDS = 60
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _lead_summary(text: str, *, max_sentences: int = 2, max_chars: int = 420) -> str:
    """Extractive last-resort fallback."""
    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]
    if not sentences:
        return text[:max_chars].strip()
    picked: list[str] = []
    for sentence in sentences:
        picked.append(sentence)
        if len(picked) >= max_sentences:
            break
    summary = " ".join(picked)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return summary


def _decode(result) -> str | None:
    if not result:
        return None
    summary = result[0].get("summary_text") if isinstance(result[0], dict) else str(result[0])
    summary = " ".join((summary or "").split())
    return summary or None


def _run_model(kind: str, text: str, summarizer=None) -> str | None:
    if summarizer is None:
        from app.nlp.models import get_summarizer

        summarizer = get_summarizer(kind)
    result = summarizer(
        text,
        max_length=130,
        min_length=40,
        truncation=True,
        do_sample=False,
    )
    return _decode(result)


def summarize_text(text: str | None, summarizer=None) -> str | None:
    """Return a 2–3 sentence summary using BART, then T5 if needed.

    Inputs under about 60 words are already short enough and are returned as-is.
    ``summarizer``, when injected (tests / drain scripts), is used as the only
    neural step.
    """
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return None
    if len(cleaned.split()) < _MIN_WORDS:
        return cleaned

    # Injected summarizer (tests / drain monkeypatches) — single shot.
    if summarizer is not None:
        try:
            return _run_model("bart", cleaned, summarizer=summarizer) or _lead_summary(cleaned)
        except Exception:
            logger.exception("injected summariser failed; using extractive fallback")
            return _lead_summary(cleaned)

    # Production: DistilBART (BART family), then T5-small.
    try:
        summary = _run_model("bart", cleaned)
        if summary:
            return summary
    except Exception:
        logger.exception("BART summariser failed; trying T5")

    try:
        summary = _run_model("t5", cleaned)
        if summary:
            return summary
    except Exception:
        logger.exception("T5 summariser failed; using extractive fallback")

    return _lead_summary(cleaned)
