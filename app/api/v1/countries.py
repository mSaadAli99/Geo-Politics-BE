"""Country map and country detail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import WindowFilters
from app.core.database import get_db
from app.schemas.meta import CountryDetail, CountryMapItem
from app.services import countries as country_service

router = APIRouter(prefix="/countries", tags=["countries"])


@router.get("", response_model=list[CountryMapItem])
def list_countries(filters: WindowFilters, db: Session = Depends(get_db)):
    return country_service.list_countries(db, filters)


@router.get("/{iso2}", response_model=CountryDetail)
def get_country(
    filters: WindowFilters,
    iso2: str = Path(min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    db: Session = Depends(get_db),
):
    payload = country_service.get_country(db, iso2, filters)
    if payload is None:
        raise HTTPException(status_code=404, detail="Country not found")
    return payload
