"""Dashboard statistics."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import WindowFilters, stats_filters
from app.core.database import get_db
from app.schemas.meta import CategoryStat, Overview, SentimentGroup
from app.services import stats as stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=Overview)
def overview(db: Session = Depends(get_db)):
    return stats_service.overview(db)


@router.get("/sentiment", response_model=list[SentimentGroup])
def sentiment(
    grouped: tuple = Depends(stats_filters),
    db: Session = Depends(get_db),
):
    group_by, window = grouped
    return stats_service.sentiment_breakdown(db, group_by, window)


@router.get("/categories", response_model=list[CategoryStat])
def categories(filters: WindowFilters, db: Session = Depends(get_db)):
    return stats_service.category_counts(db, filters)
