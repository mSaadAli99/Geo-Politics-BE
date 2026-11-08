"""Put articles back on the NLP queue when AI fields were skipped.

Also scrubs placeholder authors such as ``none@none.com (AFP)``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import or_, select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.ingestion.clean import clean_author  # noqa: E402
from app.models import Article  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--authors-only",
        action="store_true",
        help="Only scrub placeholder authors; do not requeue NLP",
    )
    args = parser.parse_args()
    db = SessionLocal()
    try:
        author_rows = db.scalars(
            select(Article).where(Article.author.is_not(None)).limit(5000)
        ).all()
        scrubbed = 0
        for article in author_rows:
            cleaned = clean_author(article.author)
            if cleaned != article.author:
                article.author = cleaned
                scrubbed += 1
        if args.authors_only:
            db.commit()
            print(f"authors_scrubbed={scrubbed}")
            return
        rows = db.scalars(
            select(Article)
            .where(
                Article.is_duplicate_of.is_(None),
                or_(
                    Article.summary.is_(None),
                    Article.sentiment_label.is_(None),
                    Article.category.is_(None),
                    Article.credibility_score.is_(None),
                    Article.processing_status != "done",
                ),
            )
            .order_by(Article.id.desc())
            .limit(args.limit)
        ).all()
        for article in rows:
            article.processing_status = "pending"
            article.processing_error = None
        db.commit()
        print(f"requeued={len(rows)} authors_scrubbed={scrubbed}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
