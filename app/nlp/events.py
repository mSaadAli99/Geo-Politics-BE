"""Group articles about the same story. Different outlets are not duplicates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class ClusterItem:
    id: int
    title: str
    text: str
    published_at: datetime | None = None


@dataclass
class ClusterGroup:
    member_ids: list[int]
    title: str


def cluster_items(items: list[ClusterItem], *, threshold: float = 0.55) -> list[ClusterGroup]:
    """Greedy TF-IDF clustering.

    An article joins the nearest cluster when cosine similarity is at least
    ``threshold``. Entity names should already be appended to ``text`` by the
    caller so overlap in names pulls related stories together. Clusters of one
    article are dropped.
    """
    if len(items) < 2:
        return []
    def _key(item: ClusterItem) -> tuple[int, float, int]:
        if item.published_at is None:
            return (1, 0.0, item.id)
        stamp = item.published_at
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return (0, stamp.timestamp(), item.id)

    ordered = sorted(items, key=_key)
    texts = [item.text.strip() or item.title for item in ordered]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return []
    groups: list[list[int]] = []
    centroids: list[np.ndarray] = []
    for index in range(matrix.shape[0]):
        row = matrix[index]
        if centroids:
            stacked = np.vstack(centroids)
            scores = cosine_similarity(row, stacked).ravel()
            best = int(np.argmax(scores))
            if float(scores[best]) >= threshold:
                groups[best].append(index)
                members = matrix[groups[best]]
                centroids[best] = np.asarray(members.mean(axis=0)).ravel()
                continue
        groups.append([index])
        centroids.append(np.asarray(row.todense()).ravel())
    clusters: list[ClusterGroup] = []
    for indexes, centroid in zip(groups, centroids, strict=True):
        if len(indexes) < 2:
            continue
        member_matrix = matrix[indexes]
        scores = cosine_similarity(centroid.reshape(1, -1), member_matrix).ravel()
        title = ordered[indexes[int(np.argmax(scores))]].title
        clusters.append(ClusterGroup(member_ids=[ordered[i].id for i in indexes], title=title))
    return clusters
