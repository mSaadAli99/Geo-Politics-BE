"""Put articles back on the NLP queue."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models import Article  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Requeue articles for the NLP worker")
    parser.add_argument("--status", choices=["pending", "failed", "done", "all"], default="failed")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        stmt = select(Article).order_by(Article.id).limit(args.limit)
        if args.status != "all":
            stmt = stmt.where(Article.processing_status == args.status)
        rows = db.scalars(stmt).all()
        for article in rows:
            article.processing_status = "pending"
            article.processing_error = None
        db.commit()
        print(f"requeued {len(rows)} articles")
    finally:
        db.close()


if __name__ == "__main__":
    main()
