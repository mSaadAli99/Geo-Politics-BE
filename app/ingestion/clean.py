"""Pandas cleaning: HTML, whitespace, dates, language, and geopolitical relevance."""

from __future__ import annotations

import html
import re
from datetime import timezone

import pandas as pd

from app.ingestion.dedupe import domain_from_url, hash_url
from app.ingestion.types import RawArticle

CONTENT_CAP = 4000
DESCRIPTION_CAP = 1000

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_NOISE = re.compile(
    r"\b(football|soccer|nba|nfl|cricket|tennis|premier league|box office|"
    r"celebrity|hollywood|album|kardashian|movie premiere)\b",
    re.IGNORECASE,
)
_NOISE_SECTIONS = {"sport", "sports", "entertainment", "culture", "lifestyle", "fashion"}
_GEO = re.compile(
    r"\b(sanction|diplomat|embassy|ceasefire|missile|invasion|parliament|election|"
    r"tariff|refugee|military|summit|treaty|geopolit\w*|coup|airstrike|artillery|"
    r"blockade|annex\w*|nato|united nations|border|war|troops)\b",
    re.IGNORECASE,
)
_PLACEHOLDER_AUTHOR = re.compile(
    r"^(none|null|n/?a|unknown|anonymous)(@\S+)?$",
    re.IGNORECASE,
)
_FAKE_AUTHOR_EMAIL = re.compile(
    r"^(none|null|noreply|no-?reply|editorial|editor|newsroom|info|contact|admin)@\S+",
    re.IGNORECASE,
)
_ANY_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_ENGLISH_STOPS = {
    "the",
    "a",
    "of",
    "and",
    "to",
    "in",
    "for",
    "on",
    "with",
    "at",
    "by",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "this",
    "that",
    "as",
    "an",
    "or",
    "it",
    "its",
    "said",
    "after",
    "over",
    "have",
    "has",
}


def strip_html(value: str | None) -> str | None:
    """Remove tags, unescape entities, and collapse whitespace."""
    if value is None:
        return None
    text = html.unescape(_TAGS.sub(" ", str(value)))
    text = _SPACE.sub(" ", text).strip()
    return text or None


def is_english(text: str, declared: str | None = None) -> bool:
    """Keep English. A declared language wins; otherwise use a stop-word check."""
    if declared:
        lang = declared.lower().replace("_", "-")
        return lang == "en" or lang.startswith("en-")
    words = re.findall(r"[A-Za-z']+", (text or "").lower())
    if len(words) < 8:
        letters = re.findall(r"[A-Za-z]", text or "")
        return len(letters) >= 12 or len(words) == 0
    sample = words[:80]
    hits = sum(1 for word in sample if word in _ENGLISH_STOPS)
    return hits >= 3


def is_geopolitical(
    title: str,
    description: str | None,
    section: str | None,
    *,
    assume_relevant: bool,
    country_hit: bool,
) -> bool:
    """Drop sport and entertainment. Keep world-desk items and geo stories."""
    text = f"{title} {description or ''}"
    section_name = (section or "").strip().lower()
    if section_name in _NOISE_SECTIONS or _NOISE.search(text):
        return False
    if assume_relevant:
        return True
    if section_name in {"world", "politics", "international", "middle east", "africa", "asia", "europe"}:
        return True
    if country_hit or _GEO.search(text):
        return True
    return False


def _cap(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    return value[:limit]


def clean_author(value: str | None) -> str | None:
    """Normalise author strings to a plain display name.

    Examples:
    - ``none@none.com (AFP)`` → ``AFP``
    - ``editorial@africanews.com (Alexis Caraco)`` → ``Alexis Caraco``
    - bare placeholder / role emails without a name → ``None``
    """
    if value is None:
        return None
    text = _SPACE.sub(" ", str(value)).strip()
    if not text:
        return None
    paren = re.search(r"\(([^)]+)\)\s*$", text)
    named = paren.group(1).strip() if paren else None
    core = text
    if paren:
        core = text[: paren.start()].strip(" ,;-")
    if not core:
        return named or None
    if _PLACEHOLDER_AUTHOR.match(core) or _FAKE_AUTHOR_EMAIL.match(core):
        return named or None
    if _ANY_EMAIL.match(core):
        # Desk/role inboxes often put the real byline in parentheses.
        return named or None
    if core.lower() in {"none", "null", "nan", "n/a", "unknown"}:
        return named or None
    return text[:512]


def clean_articles(items: list[RawArticle]) -> pd.DataFrame:
    """Normalise a batch and drop rows the MVP should not store.

    The frame is empty when every row is filtered out. ``published_at`` values
    are timezone-aware UTC datetimes or missing.
    """
    if not items:
        return pd.DataFrame()
    from app.nlp.countries import mentions_country

    rows: list[dict] = []
    for item in items:
        title = strip_html(item.title)
        if not title or not item.url:
            continue
        description = _cap(strip_html(item.description), DESCRIPTION_CAP)
        content = _cap(strip_html(item.content_text) or description, CONTENT_CAP)
        author = clean_author(strip_html(item.author))
        blob = f"{title} {description or ''} {content or ''}"
        if not is_english(blob, item.language):
            continue
        country_hit = mentions_country(f"{title} {description or ''}")
        if not is_geopolitical(
            title,
            description,
            item.section,
            assume_relevant=item.assume_relevant,
            country_hit=country_hit,
        ):
            continue
        published = item.published_at
        if isinstance(published, pd.Timestamp):
            published = published.to_pydatetime()
        if published is not None and published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        outlet_domain = (item.outlet_domain or domain_from_url(item.url) or "").lower()
        rows.append(
            {
                "url": item.url.strip(),
                "url_hash": hash_url(item.url),
                "title": title,
                "author": author,
                "description": description,
                "content_text": content,
                "image_url": item.image_url,
                "language": "en",
                "published_at": published,
                "section": item.section,
                "outlet_name": item.outlet_name,
                "outlet_domain": outlet_domain,
            }
        )
    frame = pd.DataFrame.from_records(rows)
    if frame.empty:
        return frame
    return frame.drop_duplicates(subset=["url_hash"], keep="first").reset_index(drop=True)


def frame_records(frame: pd.DataFrame) -> list[dict]:
    """Convert a cleaned frame to plain dicts with ``None`` instead of NaN."""
    if frame.empty:
        return []
    records: list[dict] = []
    for row in frame.to_dict(orient="records"):
        item: dict = {}
        for key, value in row.items():
            if value is None:
                item[key] = None
                continue
            try:
                if pd.isna(value):
                    item[key] = None
                    continue
            except TypeError:
                pass
            if isinstance(value, pd.Timestamp):
                item[key] = None if pd.isna(value) else value.to_pydatetime()
            else:
                item[key] = value
        records.append(item)
    return records
