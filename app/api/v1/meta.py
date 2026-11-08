"""Health, categories, and sources."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.meta import CategoryCount, HealthStatus, SourceOut
from app.services import meta as meta_service

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthStatus)
def health(db: Session = Depends(get_db)):
    """Liveness plus a database ping."""
    payload = HealthStatus.model_validate(meta_service.health(db))
    if payload.db != "ok":
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))
    return payload


@router.get("/categories", response_model=list[CategoryCount])
def categories(db: Session = Depends(get_db)):
    return meta_service.list_categories(db)


@router.get("/sources", response_model=list[SourceOut])
def sources(db: Session = Depends(get_db)):
    return meta_service.list_sources(db)
