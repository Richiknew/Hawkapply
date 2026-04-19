"""
Pipeline endpoints — trigger scraping + H1B matching as a background task.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

import psycopg2.extras
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from loguru import logger
from psycopg2.extensions import connection as PGConnection

from api.dependencies import get_db, verify_api_key
from api.schemas.pipeline import (
    PipelineConfigUpdate,
    PipelineFilters,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStatus,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])

# In-process status store (single-user tool — one active run at a time)
_runs: dict[str, PipelineStatus] = {}
_lock = threading.Lock()
_cancelled: set[str] = set()  # run_ids requested to cancel


def _current_run() -> Optional[PipelineStatus]:
    with _lock:
        if not _runs:
            return None
        latest_id = max(_runs, key=lambda k: _runs[k].started_at or datetime.min)
        return _runs[latest_id]


def _is_cancelled(run_id: str) -> bool:
    with _lock:
        return run_id in _cancelled


def _build_filters() -> PipelineFilters:
    """Snapshot the current scraping config."""
    from config import settings
    try:
        from scrapers.career_scraper import GREENHOUSE, LEVER, ASHBY, SMARTRECRUITERS, WORKDAY
        company_count = len(GREENHOUSE) + len(LEVER) + len(ASHBY) + len(SMARTRECRUITERS) + len(WORKDAY)
    except Exception:
        company_count = 0
    return PipelineFilters(
        target_roles=settings.TARGET_ROLES,
        locations=settings.LOCATIONS,
        min_salary=settings.MIN_SALARY,
        posted_within_days=settings.POSTED_WITHIN_DAYS,
        min_h1b_filings=settings.MIN_H1B_FILINGS,
        require_sponsorship=settings.REQUIRE_SPONSORSHIP,
        company_count=company_count,
    )


def _run_pipeline(run_id: str, refresh_h1b: bool) -> None:
    """Execute full scrape + H1B match pipeline in a background thread."""
    with _lock:
        _runs[run_id].status = "running"
        _runs[run_id].started_at = datetime.now(tz=timezone.utc)
        _runs[run_id].message = "Starting job scrape"
        _runs[run_id].filters = _build_filters()

    try:
        logger.info(f"[pipeline:{run_id}] Starting scrape (refresh_h1b={refresh_h1b})")

        from scrapers.job_scraper import run_all_scrapers
        from scrapers.h1b_matcher import match_jobs_with_sponsors, load_or_refresh_sponsors
        from db import operations as ops

        def update_progress(message: str, total_jobs: int) -> None:
            with _lock:
                run = _runs.get(run_id)
                if not run or run.status in {"failed", "completed", "cancelled"}:
                    return
                run.message = message
                run.jobs_scraped = total_jobs

        jobs = run_all_scrapers(progress_cb=update_progress)

        if _is_cancelled(run_id):
            logger.info(f"[pipeline:{run_id}] Cancelled after scraping")
            with _lock:
                _runs[run_id].status = "cancelled"
                _runs[run_id].finished_at = datetime.now(tz=timezone.utc)
                _runs[run_id].message = "Cancelled by user"
            return

        with _lock:
            _runs[run_id].message = "Replacing existing new jobs with fresh scrape"

        new_count = ops.replace_new_jobs_batch(jobs)
        logger.info(f"[pipeline:{run_id}] Replaced new-job queue with {new_count} fresh jobs (total scraped: {len(jobs)})")

        with _lock:
            _runs[run_id].jobs_scraped = len(jobs)
            _runs[run_id].message = "Persisting scraped jobs"

        if _is_cancelled(run_id):
            logger.info(f"[pipeline:{run_id}] Cancelled before matching")
            with _lock:
                _runs[run_id].status = "cancelled"
                _runs[run_id].finished_at = datetime.now(tz=timezone.utc)
                _runs[run_id].message = "Cancelled before matching"
            return

        if refresh_h1b:
            with _lock:
                _runs[run_id].message = "Refreshing H1B sponsor dataset"
            load_or_refresh_sponsors(force_refresh=True)

        with _lock:
            _runs[run_id].message = "Matching resume against scraped jobs"
        match_jobs_with_sponsors()
        logger.info(f"[pipeline:{run_id}] H1B matching complete")

        filters = _build_filters()
        with _lock:
            _runs[run_id].message = "Applying saved pipeline filters"
        remaining_count = ops.apply_pipeline_filters_to_new_jobs(
            min_salary=filters.min_salary,
            posted_within_days=filters.posted_within_days,
            require_sponsorship=filters.require_sponsorship,
            min_h1b_filings=filters.min_h1b_filings,
        )

        with _lock:
            _runs[run_id].status = "completed"
            _runs[run_id].finished_at = datetime.now(tz=timezone.utc)
            _runs[run_id].jobs_matched = remaining_count
            _runs[run_id].message = f"Scraped {len(jobs)} jobs, kept {remaining_count} after filters"

    except Exception as exc:
        logger.exception(f"[pipeline:{run_id}] Pipeline failed")
        with _lock:
            _runs[run_id].status = "failed"
            _runs[run_id].finished_at = datetime.now(tz=timezone.utc)
            _runs[run_id].error = str(exc)


@router.get("/config", response_model=PipelineFilters)
def get_pipeline_config():
    """Return the current scraping configuration (target roles, locations, salary, H1B settings)."""
    return _build_filters()


@router.put("/config", response_model=PipelineFilters)
def update_pipeline_config(body: PipelineConfigUpdate):
    """Persist pipeline filters for future runs."""
    from config import settings

    saved = settings.save_pipeline_config(
        target_roles=body.target_roles,
        locations=body.locations,
        min_salary=body.min_salary,
        posted_within_days=body.posted_within_days,
        min_h1b_filings=body.min_h1b_filings,
        require_sponsorship=body.require_sponsorship,
    )

    filters = _build_filters()
    filters.target_roles = saved["target_roles"]
    filters.locations = saved["locations"]
    filters.min_salary = saved["min_salary"]
    filters.posted_within_days = saved["posted_within_days"]
    filters.min_h1b_filings = saved["min_h1b_filings"]
    filters.require_sponsorship = saved["require_sponsorship"]
    return filters


@router.post("/run", response_model=PipelineRunResponse, status_code=202)
def run_pipeline(
    body: PipelineRunRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger the full scrape + H1B matching pipeline.
    Returns immediately with a run_id; poll /pipeline/status to track progress.
    Only one run is allowed at a time.
    """
    current = _current_run()
    if current and current.status == "running":
        raise HTTPException(
            status_code=409,
            detail="A pipeline run is already in progress",
        )

    run_id = str(uuid.uuid4())[:8]
    with _lock:
        _runs[run_id] = PipelineStatus(
            run_id=run_id,
            status="pending",
            started_at=None,
            finished_at=None,
            message="Queued",
            filters=_build_filters(),
        )

    background_tasks.add_task(_run_pipeline, run_id, body.refresh_h1b)
    logger.info(f"[pipeline:{run_id}] Queued (refresh_h1b={body.refresh_h1b})")

    return PipelineRunResponse(
        run_id=run_id,
        status="pending",
        message="Pipeline queued — poll /pipeline/status for updates",
    )


@router.get("/status", response_model=PipelineStatus)
def get_status(run_id: Optional[str] = Query(None)):
    """Return the status of a specific run, or the most recent run if omitted."""
    if run_id:
        with _lock:
            run = _runs.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    current = _current_run()
    if not current:
        raise HTTPException(status_code=404, detail="No pipeline runs yet")
    return current


@router.get("/runs")
def list_runs():
    """List all pipeline runs in this session (most recent first)."""
    with _lock:
        runs = sorted(
            _runs.values(),
            key=lambda r: r.started_at or datetime.min,
            reverse=True,
        )
    return runs


@router.post("/cancel/{run_id}", status_code=200)
def cancel_run(run_id: str):
    """
    Request cancellation of a running pipeline.
    The run will stop at the next cancellation checkpoint (between scraping and matching).
    """
    with _lock:
        if run_id not in _runs:
            raise HTTPException(status_code=404, detail="Run not found")
        current_status = _runs[run_id].status
        if current_status in {"completed", "failed", "cancelled"}:
            return {"message": f"Run already finished with status: {current_status}"}
        if current_status not in {"pending", "running"}:
            raise HTTPException(
                status_code=409,
                detail=f"Run is not cancellable (status: {current_status})",
            )
        _cancelled.add(run_id)
        _runs[run_id].message = "Cancellation requested…"

    logger.info(f"[pipeline:{run_id}] Cancellation requested")
    return {"message": "Cancellation requested — will stop at next checkpoint"}
