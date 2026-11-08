"""FastAPI application. This process reads the database and does not load NLP models."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, articles, countries, events, meta, stats, timeline, trending
from app.core.config import settings
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    if settings.enable_scheduler:
        logger.warning(
            "ENABLE_SCHEDULER is true, but the API process does not run jobs. "
            "Start them with: python -m app.scheduler.run_scheduler"
        )
    logger.info("GeoPolitics API ready")
    yield


app = FastAPI(
    title="GeoPolitics AI",
    version="1.0.0",
    summary="Collects, analyses, and serves geopolitical news.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router, prefix="/api/v1")
app.include_router(articles.router, prefix="/api/v1")
app.include_router(countries.router, prefix="/api/v1")
app.include_router(trending.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(timeline.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

# Same health payload at the root for process managers.
app.add_api_route("/health", meta.health, methods=["GET"], tags=["meta"])
