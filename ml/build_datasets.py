"""Build bootstrap labelled CSVs so training can run before hand labels exist.

These rows are original template text, not copied articles. Replace them with
team-labelled stories before quoting the metrics in a report.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "ml" / "datasets"

COUNTRIES = [
    "Pakistan",
    "India",
    "Ukraine",
    "China",
    "France",
    "Germany",
    "Japan",
    "Egypt",
    "Kenya",
    "Brazil",
]
CITIES = ["Islamabad", "New Delhi", "Kyiv", "Beijing", "Paris", "Berlin", "Cairo", "Nairobi"]

CATEGORY_LINES = {
    "politics": [
        "The president faced a vote in parliament after the opposition launched a campaign.",
        "Lawmakers opened an election campaign and argued over the next ballot.",
        "The prime minister asked parliament to back a new cabinet before the vote.",
    ],
    "economy": [
        "Inflation and a rising debt load pushed the IMF to review the trade outlook.",
        "Markets fell after a new tariff and a warning of recession.",
        "The oil price jump revived a trade argument and a GDP downgrade.",
    ],
    "conflict": [
        "Troops reported shelling and a missile strike near the ceasefire line.",
        "An airstrike hit a town as militants and artillery moved overnight.",
        "The invasion talk returned after soldiers were killed near the border.",
    ],
    "international_relations": [
        "An ambassador opened a summit and discussed a treaty at the embassy.",
        "Diplomats at the United Nations and NATO held bilateral talks.",
        "The embassy confirmed a summit on a new bilateral treaty.",
    ],
    "global_affairs": [
        "A humanitarian team tracked refugee needs after the climate disaster.",
        "Health agencies warned that emissions and a pandemic risk were rising.",
        "Aid workers described a global health emergency and a refugee camp.",
    ],
}

SENTIMENT_LINES = {
    "positive": [
        "Leaders welcomed a cooperation deal and said growth could recover.",
        "The ceasefire held and both sides praised the aid agreement.",
        "Markets rose after a recovery plan and a calm diplomatic breakthrough.",
    ],
    "negative": [
        "An attack killed civilians and the crisis deepened overnight.",
        "Sanctions and a violent crackdown drove the economy toward collapse.",
        "Protests turned violent after the collapse of the peace talks.",
    ],
    "neutral": [
        "Officials said a meeting is scheduled and a report will follow.",
        "According to the ministry, talks are planned for next week.",
        "A spokesperson said the committee will review the file on Thursday.",
    ],
}


def _write(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_categories(rng: random.Random) -> list[dict]:
    rows = []
    for category, lines in CATEGORY_LINES.items():
        for index in range(160):
            country = COUNTRIES[index % len(COUNTRIES)]
            other = COUNTRIES[(index + 3) % len(COUNTRIES)]
            city = CITIES[index % len(CITIES)]
            line = lines[index % len(lines)]
            title = f"{country} update {index + 1}: {line.split('.')[0]}"
            text = (
                f"In {city}, {country} and {other} were in the news. {line} "
                f"Editors noted item {index + 1} as a {category.replace('_', ' ')} story."
            )
            rows.append({"title": title, "text": text, "category": category})
    rng.shuffle(rows)
    return rows


def build_sentiment(rng: random.Random) -> list[dict]:
    rows = []
    for label, lines in SENTIMENT_LINES.items():
        for index in range(100):
            country = COUNTRIES[index % len(COUNTRIES)]
            line = lines[index % len(lines)]
            rows.append({"text": f"{country}: {line}", "label": label})
    rng.shuffle(rows)
    return rows


def build_summaries(rng: random.Random) -> list[dict]:
    rows = []
    topics = [
        ("border crossing", "reopen a border crossing"),
        ("grain shipment", "restart grain shipments"),
        ("energy grid", "repair the energy grid"),
        ("prisoner exchange", "arrange a prisoner exchange"),
        ("climate fund", "fund climate adaptation"),
    ]
    for index in range(100):
        left = COUNTRIES[index % len(COUNTRIES)]
        right = COUNTRIES[(index + 4) % len(COUNTRIES)]
        city = CITIES[index % len(CITIES)]
        noun, action = topics[index % len(topics)]
        text = (
            f"Officials met on Monday in {city} and spoke to reporters. "
            f"{left} and {right} agreed to {action} next month. "
            f"Analysts said the {noun} could take weeks to put in place."
        )
        reference = f"{left} and {right} plan to {action}."
        rows.append({"text": text, "reference": reference})
    rng.shuffle(rows)
    return rows


def main() -> None:
    rng = random.Random(7)
    _write(DATA / "category_labels.csv", build_categories(rng), ["title", "text", "category"])
    _write(DATA / "sentiment_labels.csv", build_sentiment(rng), ["text", "label"])
    _write(DATA / "summary_references.csv", build_summaries(rng), ["text", "reference"])
    print(f"wrote datasets in {DATA}")


if __name__ == "__main__":
    main()
