"""Evaluate sentiment labels.

The live pipeline uses the Hugging Face RoBERTa model. This script scores a
TF-IDF baseline on the labelled CSV so the report has numbers without a
multi-gigabyte download. Pass --use-hf to score the production model instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

DATA = ROOT / "ml" / "datasets" / "sentiment_labels.csv"
REPORT = ROOT / "ml" / "artifacts" / "sentiment_eval.json"


def _metrics(y_true, y_pred, labels: list[str]) -> dict:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "labels": labels,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "per_class": classification_report(
            y_true, y_pred, labels=labels, output_dict=True, zero_division=0
        ),
    }


def evaluate_baseline() -> dict:
    frame = pd.read_csv(DATA)
    x_train, x_test, y_train, y_test = train_test_split(
        frame["text"].tolist(),
        frame["label"].tolist(),
        test_size=0.2,
        random_state=42,
        stratify=frame["label"].tolist(),
    )
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), stop_words="english")),
            ("clf", LogisticRegression(max_iter=400, class_weight="balanced")),
        ]
    )
    model.fit(x_train, y_train)
    labels = ["negative", "neutral", "positive"]
    metrics = _metrics(y_test, model.predict(x_test), labels)
    metrics["model_name"] = "tfidf_logreg_baseline"
    metrics["task"] = "sentiment"
    metrics["dataset"] = "ml/datasets/sentiment_labels.csv"
    metrics["note"] = (
        "Baseline for the labelled sheet. Production sentiment is "
        "cardiffnlp/twitter-roberta-base-sentiment-latest; run with --use-hf."
    )
    return metrics


def evaluate_hf() -> dict:
    from app.core.config import settings
    from app.nlp.sentiment import sentiment_text

    frame = pd.read_csv(DATA)
    _, x_test, _, y_test = train_test_split(
        frame["text"].tolist(),
        frame["label"].tolist(),
        test_size=0.2,
        random_state=42,
        stratify=frame["label"].tolist(),
    )
    predicted = []
    for text in x_test:
        label, _score = sentiment_text(text)
        predicted.append(label or "neutral")
    labels = ["negative", "neutral", "positive"]
    metrics = _metrics(y_test, predicted, labels)
    metrics["model_name"] = settings.sentiment_model
    metrics["task"] = "sentiment"
    metrics["dataset"] = "ml/datasets/sentiment_labels.csv"
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-hf", action="store_true")
    args = parser.parse_args()
    if not DATA.exists():
        from ml.build_datasets import main as build

        build()
    metrics = evaluate_hf() if args.use_hf else evaluate_baseline()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({key: metrics[key] for key in ("model_name", "accuracy", "f1_macro")}, indent=2))


if __name__ == "__main__":
    main()
