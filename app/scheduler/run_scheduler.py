"""Separate process entrypoint for APScheduler.

Run with ENABLE_SCHEDULER=true. Uvicorn workers must not start this.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler

from app.core.config import settings
from app.core.logging import setup_logging
from app.scheduler.jobs import cluster_job, ingest_job, process_job, trending_job

logger = logging.getLogger(__name__)


def _on_event(event) -> None:
    if event.exception:
        logger.error("job %s failed", event.job_id)
    else:
        logger.info("job %s finished", event.job_id)


def main(argv: list[str] | None = None) -> None:
    """Start the blocking scheduler, or run every job once."""
    parser = argparse.ArgumentParser(description="GeoPolitics AI scheduler")
    parser.add_argument("--once", action="store_true", help="Run ingest, process, cluster, and trending once")
    args = parser.parse_args(argv)
    setup_logging()
    if not settings.enable_scheduler:
        logger.error(
            "ENABLE_SCHEDULER is false. Set it to true only for the scheduler process, then start again."
        )
        sys.exit(1)
    if settings.hf_home:
        os.environ["HF_HOME"] = settings.hf_home
    if args.once:
        ingest_job()
        process_job()
        cluster_job()
        trending_job()
        return
    scheduler = BlockingScheduler(executors={"default": ThreadPoolExecutor(max_workers=1)})
    scheduler.add_listener(_on_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.add_job(
        ingest_job,
        "interval",
        minutes=settings.ingest_interval_minutes,
        id="ingest",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        process_job,
        "interval",
        minutes=2,
        id="process",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        cluster_job,
        "interval",
        minutes=15,
        id="cluster",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        trending_job,
        "interval",
        minutes=30,
        id="trending",
        max_instances=1,
        coalesce=True,
    )
    # Kick off NLP immediately so the queue does not wait for the first interval.
    scheduler.add_job(process_job, id="process_bootstrap", max_instances=1)
    logger.info("scheduler started")
    scheduler.start()


if __name__ == "__main__":
    main()
