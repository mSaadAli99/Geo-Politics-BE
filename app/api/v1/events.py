"""Event clusters and the compare-sources view."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import EventFilters
from app.core.database import get_db
from app.schemas.events import EventDetail, EventPage
from app.services import events as event_service

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventPage)
def list_events(filters: EventFilters, db: Session = Depends(get_db)):
    return event_service.list_events(db, filters)


@router.get("/{event_id}", response_model=EventDetail)
def get_event(event_id: int, db: Session = Depends(get_db)):
    payload = event_service.get_event(db, event_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return payload
