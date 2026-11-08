"""Named entity recognition with mention counts."""

from __future__ import annotations

_ALLOWED = {"PER", "ORG", "LOC", "MISC"}


def _type_of(label: str) -> str:
    token = label.upper().split("-")[-1]
    if token in _ALLOWED:
        return token
    return "MISC"


def extract_entities(text: str | None, ner_pipeline=None) -> list[tuple[str, str, int]]:
    """Return ``(text, type, mentions)`` for PER, ORG, LOC, and MISC.

    ``type`` is one of those four codes. The pipeline is injected in tests.
    """
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    if ner_pipeline is None:
        from app.nlp.models import get_ner

        ner_pipeline = get_ner()
    rows = ner_pipeline(cleaned[:2000]) or []
    counts: dict[tuple[str, str], int] = {}
    display: dict[tuple[str, str], str] = {}
    for row in rows:
        score = float(row.get("score") or 0)
        if score < 0.5:
            continue
        word = " ".join(str(row.get("word") or "").replace("##", "").split())
        if len(word) < 2:
            continue
        kind = _type_of(str(row.get("entity_group") or row.get("entity") or "MISC"))
        key = (word.lower(), kind)
        counts[key] = counts.get(key, 0) + 1
        display.setdefault(key, word)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0][0]))
    return [(display[key], key[1], mentions) for key, mentions in ranked]
