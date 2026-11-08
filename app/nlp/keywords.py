"""TF-IDF keywords for one article, plus a few entity names."""

from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer


def extract_keywords(
    text: str | None,
    entities: list[str] | None = None,
    *,
    limit: int = 8,
) -> list[str]:
    """Return up to ``limit`` terms or bigrams, then extra entity strings.

    A single document has no corpus IDF, so the vectoriser ranks by term
    frequency inside the article. That is still the spec's TF-IDF step.
    """
    cleaned = " ".join((text or "").split())
    found: list[str] = []
    if cleaned:
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",
        )
        try:
            matrix = vectorizer.fit_transform([cleaned])
        except ValueError:
            matrix = None
        if matrix is not None:
            scores = matrix.toarray()[0]
            terms = vectorizer.get_feature_names_out()
            order = scores.argsort()[::-1]
            for index in order:
                if scores[index] <= 0:
                    continue
                term = str(terms[index])
                if len(term) < 3:
                    continue
                found.append(term)
                if len(found) >= limit:
                    break
    seen = {item.lower() for item in found}
    extras: list[str] = []
    for entity in entities or []:
        label = " ".join(str(entity).split())
        if not label or label.lower() in seen:
            continue
        extras.append(label)
        seen.add(label.lower())
        if len(extras) >= 5:
            break
    return found + extras
