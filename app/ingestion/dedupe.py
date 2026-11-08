"""URL canonicalisation and near-duplicate detection."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "ref", "ref_src", "ref_url"}


def domain_from_url(url: str) -> str:
    """Host of a URL without a leading www."""
    host = urlsplit(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def canonicalize_url(url: str) -> str:
    """Drop fragments and tracking parameters so the same story hashes once.

    The original URL is what we store and show. The hash is of this form.
    """
    raw = (url or "").strip()
    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING
    ]
    kept.sort()
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((scheme, netloc, path, urlencode(kept), ""))


def hash_url(url: str) -> str:
    """SHA-256 of the canonical URL."""
    return hashlib.sha256(canonicalize_url(url).encode("utf-8")).hexdigest()


def find_near_duplicate(
    candidate: str,
    corpus: list[tuple[int, str]],
    *,
    threshold: float = 0.9,
) -> int | None:
    """Return the id of a same-source article with cosine similarity >= threshold.

    The caller must pass only recent articles from the same source. Stories
    from other outlets are not duplicates; clustering turns those into events.
    """
    text = " ".join((candidate or "").split())
    usable = [(item_id, body.strip()) for item_id, body in corpus if body and body.strip()]
    if not text or not usable:
        return None
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    try:
        matrix = vectorizer.fit_transform([body for _, body in usable] + [text])
    except ValueError:
        return None
    scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
    if scores.size == 0:
        return None
    index = int(np.argmax(scores))
    if float(scores[index]) >= threshold:
        return usable[index][0]
    return None
