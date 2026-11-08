"""Story timeline."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import TimelineFilters
from app.core.database import get_db
from app.schemas.events import TimelineOut
from app.services.timeline import build_timeline

router = APIRouter(tags=["timeline"])


@router.get("/timeline", response_model=TimelineOut)
def timeline(filters: TimelineFilters, db: Session = Depends(get_db)):
    return build_timeline(db, filters)
