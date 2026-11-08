"""Train the TF-IDF + logistic regression category model."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

DATA = ROOT / "ml" / "datasets" / "category_labels.csv"
MODEL = ROOT / "ml" / "artifacts" / "classifier.joblib"
REPORT = ROOT / "ml" / "artifacts" / "classifier_train.json"


def load_split(seed: int = 42):
    """80/20 stratified split shared with the evaluation script."""
    frame = pd.read_csv(DATA)
    text = (frame["title"].fillna("") + " " + frame["text"].fillna("")).tolist()
    labels = frame["category"].tolist()
    return train_test_split(text, labels, test_size=0.2, random_state=seed, stratify=labels)


def build_pipeline() -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(ngram_range=(1, 2), stop_words="english", min_df=2),
            ),
            (
                "clf",
                LogisticRegression(max_iter=500, class_weight="balanced"),
            ),
        ]
    )


def main() -> None:
    if not DATA.exists():
        from ml.build_datasets import main as build

        build()
    x_train, x_test, y_train, y_test = load_split()
    model = build_pipeline()
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    metrics = {
        "accuracy": accuracy_score(y_test, predicted),
        "precision_macro": precision_score(y_test, predicted, average="macro", zero_division=0),
        "recall_macro": recall_score(y_test, predicted, average="macro", zero_division=0),
        "f1_macro": f1_score(y_test, predicted, average="macro", zero_division=0),
        "train_rows": len(x_train),
        "test_rows": len(x_test),
    }
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL)
    REPORT.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"saved {MODEL}")


if __name__ == "__main__":
    main()
