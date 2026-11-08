"""Small query helpers shared by list endpoints."""

from __future__ import annotations

import math

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def page_count(total: int, page_size: int) -> int:
    """Number of pages, or 0 when there are no rows."""
    if total <= 0 or page_size <= 0:
        return 0
    return math.ceil(total / page_size)


def count_stmt(db: Session, stmt: Select) -> int:
    """Count rows of a statement without keeping its ORDER BY."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    return int(total or 0)
