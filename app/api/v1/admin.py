"""Admin triggers. These never load NLP models; the worker does that."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import SessionLocal, get_db
from app.ingestion.run import ingest_all
from app.models import Article, IngestionRun
from app.schemas.events import IngestAccepted, IngestionRunOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _run_ingest(run_id: int) -> None:
    """Background fetch. Opens its own session because the request one is closed."""
    db = SessionLocal()
    try:
        runs = ingest_all(db)
        parent = db.get(IngestionRun, run_id)
        if parent is None:
            return
        parent.fetched = sum(run.fetched for run in runs)
        parent.inserted = sum(run.inserted for run in runs)
        parent.duplicates = sum(run.duplicates for run in runs)
        parent.errors = sum(run.errors for run in runs)
        parent.status = "success" if parent.errors == 0 else "partial"
        parent.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        logger.exception("admin ingest failed")
        db.rollback()
        parent = db.get(IngestionRun, run_id)
        if parent is not None:
            parent.status = "failed"
            parent.errors = 1
            parent.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


@router.post("/ingest", status_code=202, response_model=IngestAccepted)
def trigger_ingest(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Start a fetch. Processing still happens in the scheduler."""
    run = IngestionRun(
        started_at=datetime.now(timezone.utc),
        fetched=0,
        inserted=0,
        duplicates=0,
        errors=0,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background.add_task(_run_ingest, run.id)
    return {"run_id": run.id}


@router.post("/reprocess/{article_id}", status_code=202)
def reprocess(
    article_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Put an article back on the worker queue."""
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    article.processing_status = "pending"
    article.processing_error = None
    article.is_duplicate_of = None
    db.commit()
    return JSONResponse(status_code=202, content={"status": "queued", "article_id": article_id})


@router.get("/runs", response_model=list[IngestionRunOut])
def runs(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    rows = db.scalars(
        select(IngestionRun).order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc()).limit(50)
    ).all()
    return rows
