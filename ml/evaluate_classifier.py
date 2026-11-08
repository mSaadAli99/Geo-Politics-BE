"""Evaluate the saved category classifier and write a confusion matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from ml.train_classifier import load_split

MODEL = ROOT / "ml" / "artifacts" / "classifier.joblib"
REPORT = ROOT / "ml" / "artifacts" / "classifier_eval.json"
FIGURE = ROOT / "ml" / "artifacts" / "classifier_confusion_matrix.png"


def main() -> None:
    if not MODEL.exists():
        from ml.train_classifier import main as train

        train()
    model = joblib.load(MODEL)
    _, x_test, _, y_test = load_split()
    predicted = model.predict(x_test)
    labels = list(model.named_steps["clf"].classes_)
    matrix = confusion_matrix(y_test, predicted, labels=labels)
    metrics = {
        "model_name": "tfidf_logreg",
        "task": "category",
        "dataset": "ml/datasets/category_labels.csv",
        "accuracy": float(accuracy_score(y_test, predicted)),
        "precision_macro": float(precision_score(y_test, predicted, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_test, predicted, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_test, predicted, average="macro", zero_division=0)),
        "labels": labels,
        "confusion_matrix": matrix.tolist(),
        "per_class": classification_report(y_test, predicted, labels=labels, output_dict=True, zero_division=0),
    }
    REPORT.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    figure, axis = plt.subplots(figsize=(8, 6))
    image = axis.imshow(matrix, cmap="Blues")
    axis.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    axis.set_yticks(range(len(labels)), labels)
    axis.set_xlabel("Predicted")
    axis.set_ylabel("Actual")
    axis.set_title("Category confusion matrix")
    figure.colorbar(image, ax=axis)
    figure.tight_layout()
    figure.savefig(FIGURE, bbox_inches="tight")
    plt.close(figure)
    print(json.dumps({key: metrics[key] for key in ("accuracy", "precision_macro", "recall_macro", "f1_macro")}, indent=2))
    _maybe_store(metrics)


def _maybe_store(metrics: dict) -> None:
    try:
        from app.core.database import SessionLocal
        from app.models import ModelEvaluation
        from datetime import datetime, timezone

        db = SessionLocal()
        try:
            db.add(
                ModelEvaluation(
                    model_name=metrics["model_name"],
                    task=metrics["task"],
                    metrics=metrics,
                    dataset=metrics["dataset"],
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        print(f"skipped database write: {exc}")


if __name__ == "__main__":
    main()
