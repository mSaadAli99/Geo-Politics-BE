"""Trending topics."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.meta import TrendingTopic
from app.services.trending import list_trending

router = APIRouter(tags=["trending"])


@router.get("/trending", response_model=list[TrendingTopic])
def trending(
    db: Session = Depends(get_db),
    window: Literal["24h", "7d"] = Query("24h"),
    limit: int = Query(10, ge=1, le=50),
):
    return list_trending(db, window=window, limit=limit)
