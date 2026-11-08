"""Lazy Hugging Face models.

The API process must not call these. Only the scheduler worker should.
"""

from __future__ import annotations

import logging
import os

from app.core.config import settings

logger = logging.getLogger(__name__)

_summarizers: dict[str, object] = {}
_sentiment = None
_ner = None

# Proposal stack: BART-family (DistilBART) + T5. Both load for the worker.
DEFAULT_BART_MODEL = "sshleifer/distilbart-cnn-12-6"
DEFAULT_T5_MODEL = "t5-small"


def _prepare_cache() -> None:
    if settings.hf_home:
        os.environ["HF_HOME"] = settings.hf_home


def _is_t5(model_name: str) -> bool:
    return "t5" in (model_name or "").lower()


def bart_model_name() -> str:
    """Primary BART-family summariser (DistilBART by default)."""
    name = (settings.summary_model or DEFAULT_BART_MODEL).strip()
    if _is_t5(name):
        return DEFAULT_BART_MODEL
    return name or DEFAULT_BART_MODEL


def t5_model_name() -> str:
    """Secondary T5 summariser used when BART fails or as explicit alternate."""
    name = (settings.summary_model_t5 or DEFAULT_T5_MODEL).strip()
    return name or DEFAULT_T5_MODEL


def _load_seq2seq(model_name: str):
    """Build a callable with the same shape as the old summarization pipeline."""
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    logger.info("loading summariser %s", model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    model.eval()
    t5 = _is_t5(model_name)

    def _run(
        payload: str,
        max_length: int = 130,
        min_length: int = 40,
        truncation: bool = True,
        do_sample: bool = False,
    ):
        text = payload
        if t5 and not str(payload).lower().startswith("summarize:"):
            text = "summarize: " + payload
        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=truncation,
            max_length=512 if t5 else 1024,
        )
        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_length=max_length,
                min_length=min_length,
                do_sample=do_sample,
            )
        decoded = tokenizer.decode(output_ids[0], skip_special_tokens=True)
        return [{"summary_text": decoded}]

    return _run


def get_summarizer(kind: str = "bart"):
    """Load a summarisation model once.

    ``kind`` is ``bart`` (DistilBART / BART family) or ``t5``.
    Transformers v5 removed the ``summarization`` pipeline task, so we call
    the seq2seq model directly.
    """
    key = "t5" if kind == "t5" else "bart"
    if key not in _summarizers:
        _prepare_cache()
        model_name = t5_model_name() if key == "t5" else bart_model_name()
        _summarizers[key] = _load_seq2seq(model_name)
    return _summarizers[key]


def get_sentiment():
    """Load the 3-class sentiment pipeline once, on CPU."""
    global _sentiment
    if _sentiment is None:
        _prepare_cache()
        from transformers import pipeline

        logger.info("loading sentiment model %s", settings.sentiment_model)
        _sentiment = pipeline(
            "sentiment-analysis",
            model=settings.sentiment_model,
            device=-1,
            truncation=True,
            max_length=512,
        )
    return _sentiment


def get_ner():
    """Load the NER pipeline once, on CPU."""
    global _ner
    if _ner is None:
        _prepare_cache()
        from transformers import pipeline

        logger.info("loading NER model %s", settings.ner_model)
        _ner = pipeline(
            "token-classification",
            model=settings.ner_model,
            aggregation_strategy="simple",
            device=-1,
        )
    return _ner
