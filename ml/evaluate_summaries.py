"""ROUGE for summaries.

Without --use-hf this scores an extractive lead baseline against the reference
file. With --use-hf it scores the live DistilBART (BART-family) model and
t5-small using the same seq2seq path as production.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from rouge_score import rouge_scorer

DATA = ROOT / "ml" / "datasets" / "summary_references.csv"
REPORT = ROOT / "ml" / "artifacts" / "summary_eval.json"

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def lead_summary(text: str) -> str:
    """First two sentences, used when the neural models are not loaded."""
    parts = [part.strip() for part in _SENTENCE.split(text.strip()) if part.strip()]
    return " ".join(parts[:2])


def _average(pairs: list[tuple[str, str]]) -> dict[str, float]:
    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
    totals = {"rouge1": 0.0, "rouge2": 0.0, "rougeL": 0.0}
    if not pairs:
        return totals
    for prediction, reference in pairs:
        scores = scorer.score(reference, prediction)
        for key in totals:
            totals[key] += scores[key].fmeasure
    return {key: round(value / len(pairs), 4) for key, value in totals.items()}


def _hf_summary(model_name: str, text: str) -> str:
    """Match production: AutoModelForSeq2SeqLM, not the removed pipeline task."""
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    model.eval()
    payload = text
    if "t5" in model_name.lower():
        payload = "summarize: " + text
    inputs = tokenizer(
        payload,
        return_tensors="pt",
        truncation=True,
        max_length=512 if "t5" in model_name.lower() else 1024,
    )
    with torch.no_grad():
        output_ids = model.generate(**inputs, max_length=80, min_length=15, do_sample=False)
    return tokenizer.decode(output_ids[0], skip_special_tokens=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-hf", action="store_true")
    parser.add_argument("--limit", type=int, default=20, help="Rows to send through HF models")
    args = parser.parse_args()
    if not DATA.exists():
        from ml.build_datasets import main as build

        build()
    frame = pd.read_csv(DATA)
    lead_pairs = [
        (lead_summary(text), reference)
        for text, reference in zip(frame["text"], frame["reference"], strict=True)
    ]
    report = {
        "dataset": "ml/datasets/summary_references.csv",
        "lead_baseline": _average(lead_pairs),
        "note": (
            "Production uses DistilBART then T5-small. "
            "Pass --use-hf to score both neural models."
        ),
    }
    if args.use_hf:
        from app.nlp.models import bart_model_name, t5_model_name

        sample = frame.head(args.limit)
        bart_name = bart_model_name()
        t5_name = t5_model_name()
        bart_pairs = []
        t5_pairs = []
        for text, reference in zip(sample["text"], sample["reference"], strict=True):
            bart_pairs.append((_hf_summary(bart_name, text), reference))
            t5_pairs.append((_hf_summary(t5_name, text), reference))
        report["bart"] = {"model": bart_name, "rows": args.limit, **_average(bart_pairs)}
        report["t5"] = {"model": t5_name, "rows": args.limit, **_average(t5_pairs)}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
