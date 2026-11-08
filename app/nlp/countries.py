"""Map text and location entities onto ISO country codes."""

from __future__ import annotations

import json
import re
from functools import lru_cache

from app.core.config import BASE_DIR

DATA_DIR = BASE_DIR / "app" / "data"

# Abbreviations that are safe to read as countries when they appear in capitals.
_TOKEN_MAP = {
    "US": "US",
    "UK": "GB",
    "GB": "GB",
    "UA": "UA",
    "RU": "RU",
    "CN": "CN",
    "PK": "PK",
    "IL": "IL",
    "IR": "IR",
    "KP": "KP",
    "KR": "KR",
    "JP": "JP",
    "FR": "FR",
    "DE": "DE",
    "TR": "TR",
    "AE": "AE",
    "IQ": "IQ",
    "SY": "SY",
    "YE": "YE",
    "AF": "AF",
    "TW": "TW",
    "PS": "PS",
    "EU": "",
    "UN": "",
}
_TOKEN = re.compile(r"\b([A-Z]{2})\b")


@lru_cache
def _phrases() -> tuple[tuple[str, str], ...]:
    """Longest-first ``(phrase, iso2)``. An empty iso2 means 'occupy and skip'."""
    aliases: dict[str, str] = json.loads((DATA_DIR / "country_aliases.json").read_text(encoding="utf-8"))
    phrases: dict[str, str] = {key.lower(): value for key, value in aliases.items()}
    import pycountry

    for country in pycountry.countries:
        for attr in ("name", "official_name", "common_name"):
            value = getattr(country, attr, None)
            if value and len(value) >= 4:
                phrases.setdefault(value.lower(), country.alpha_2)
    ordered = tuple(sorted(phrases.items(), key=lambda item: len(item[0]), reverse=True))
    return ordered


@lru_cache
def centroids() -> dict[str, dict]:
    """iso2 -> centroid record from the bundled JSON file."""
    rows = json.loads((DATA_DIR / "country_centroids.json").read_text(encoding="utf-8"))
    return {row["iso2"]: row for row in rows}


def _boundary(text: str, start: int, end: int) -> bool:
    if start > 0 and text[start - 1].isalnum():
        return False
    if end < len(text) and text[end].isalnum():
        return False
    return True


def _scan(text: str) -> dict[str, int]:
    if not text:
        return {}
    lower = text.lower()
    occupied = [False] * len(lower)
    counts: dict[str, int] = {}
    for phrase, code in _phrases():
        start = 0
        while True:
            found = lower.find(phrase, start)
            if found < 0:
                break
            end = found + len(phrase)
            if _boundary(lower, found, end) and not any(occupied[found:end]):
                for index in range(found, end):
                    occupied[index] = True
                if code:
                    counts[code] = counts.get(code, 0) + 1
            start = found + 1
    for match in _TOKEN.finditer(text):
        if any(occupied[match.start() : match.end()]):
            continue
        mapped = _TOKEN_MAP.get(match.group(1))
        if mapped:
            counts[mapped] = counts.get(mapped, 0) + 1
    return counts


def detect_countries(text: str, locations: list[str] | None = None) -> list[tuple[str, int]]:
    """Return ``(iso2, mentions)`` sorted by mentions, then code.

    The first item is the primary country. Location strings from NER are
    scanned as well as the article text.
    """
    counts = _scan(text or "")
    for location in locations or []:
        for code, mentions in _scan(location).items():
            counts[code] = counts.get(code, 0) + mentions
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [(code, mentions) for code, mentions in ranked if mentions > 0]


def mentions_country(text: str) -> bool:
    """True when the text names at least one country."""
    return bool(detect_countries(text))


def country_meta(iso2: str) -> dict | None:
    """Name, ISO3, coordinates, and region for a code, if we know it."""
    code = iso2.upper()
    centroid = centroids().get(code)
    if code == "XK":
        return {
            "iso2": "XK",
            "iso3": "XKX",
            "name": "Kosovo",
            "lat": None if not centroid else centroid.get("lat"),
            "lng": None if not centroid else centroid.get("lng"),
            "region": None if not centroid else centroid.get("region"),
        }
    import pycountry

    country = pycountry.countries.get(alpha_2=code)
    if country is None and centroid is None:
        return None
    return {
        "iso2": code,
        "iso3": getattr(country, "alpha_3", None) if country else (centroid or {}).get("iso3"),
        "name": getattr(country, "name", None) if country else (centroid or {}).get("name"),
        "lat": None if not centroid else centroid.get("lat"),
        "lng": None if not centroid else centroid.get("lng"),
        "region": None if not centroid else centroid.get("region"),
    }
