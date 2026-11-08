"""Process every pending article until the NLP queue is empty.

Uses a fast extractive summary for the backlog so CPU summarisation does not
take many hours. Sentiment + NER still use the Hugging Face models.
New articles processed by the normal scheduler still use BART when available.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.models import Article  # noqa: E402
from app.nlp import summarize as summarize_mod  # noqa: E402
from app.nlp.pipeline import process_pending  # noqa: E402

logger = logging.getLogger(__name__)
BATCH = 40
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _fast_summary(text: str | None, summarizer=None) -> str | None:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return None
    parts = [part.strip() for part in _SENTENCE.split(cleaned) if part.strip()]
    if not parts:
        return cleaned[:400]
    return " ".join(parts[:3])[:600]


def _pending(db) -> int:
    return int(
        db.scalar(
            select(func.count(Article.id)).where(
                Article.processing_status.in_(("pending", "processing")),
                Article.is_duplicate_of.is_(None),
            )
        )
        or 0
    )


def main() -> None:
    setup_logging()
    # Skip BART for this backlog drain — it is the bottleneck on CPU.
    # Patch both the summarize module and the pipeline import used at runtime.
    summarize_mod.summarize_text = _fast_summary  # type: ignore[assignment]
    import app.nlp.pipeline as pipeline_mod

    pipeline_mod.summarize_text = _fast_summary  # type: ignore[assignment]

    from app.nlp.models import get_ner, get_sentiment

    logger.info("warming sentiment + NER (extractive summaries for speed)")
    get_sentiment()
    get_ner()
    logger.info("models ready")

    total = 0
    while True:
        db = SessionLocal()
        try:
            left = _pending(db)
            print(f"pending_before_batch={left}", flush=True)
            if left == 0:
                break
            done = process_pending(db, BATCH)
            total += done
            print(f"batch_done={done} drained_total={total}", flush=True)
            if done == 0:
                stuck = db.scalars(
                    select(Article).where(Article.processing_status == "processing").limit(100)
                ).all()
                for article in stuck:
                    article.processing_status = "pending"
                if stuck:
                    db.commit()
                    print(f"reset_stuck={len(stuck)}", flush=True)
                    continue
                break
        except Exception:
            logger.exception("drain batch failed")
            db.rollback()
        finally:
            db.close()

    db = SessionLocal()
    try:
        print(f"drained_total={total} pending_left={_pending(db)}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
