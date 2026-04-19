"""
Match endpoints — run resume-JD matching and retrieve results.
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
from api.schemas.match import MatchRunRequest, MatchRunResponse

router = APIRouter(dependencies=[Depends(verify_api_key)])

_match_runs: dict[str, dict] = {}
_lock = threading.Lock()


def _preselect_jobs(jobs: list[dict], job_limit: int) -> list[dict]:
    from parsers.jd_parser import parse_jd_local
    from parsers.resume_matcher import match_resume_fast

    ranked_jobs: list[dict] = []

    for job in jobs:
        description = job.get("description", "") or ""
        if not description.strip():
            continue

        parsed_local = parse_jd_local(description)
        fast_result = match_resume_fast(parsed_local)
        h1b_score = float(job.get("h1b_score") or 0)
        preliminary_combined = round(fast_result["total_score"] * 0.6 + h1b_score * 0.4, 1)

        enriched_job = dict(job)
        enriched_job["_parsed_jd_local"] = parsed_local
        enriched_job["_fast_result"] = fast_result
        enriched_job["_preliminary_combined"] = preliminary_combined
        ranked_jobs.append(enriched_job)

    ranked_jobs.sort(
        key=lambda job: (job["_preliminary_combined"], float(job.get("h1b_score") or 0)),
        reverse=True,
    )
    return ranked_jobs[:job_limit]


def _run_matching(run_id: str, limit: int, use_ai: bool, ai_threshold: float) -> None:
    with _lock:
        _match_runs[run_id]["status"] = "running"
        _match_runs[run_id]["started_at"] = datetime.now(tz=timezone.utc).isoformat()
        _match_runs[run_id]["message"] = "Rule-ranking jobs before AI matching"

    try:
        from db import operations as ops
        from parsers.jd_parser import parse_jd
        from parsers.resume_matcher import match_resume_fast, match_resume_ai

        candidate_pool_limit = max(limit * 20, 1000)
        jobs = ops.get_jobs(status="new", limit=candidate_pool_limit)
        selected_jobs = _preselect_jobs(jobs, job_limit=limit)
        logger.info(
            f"[match:{run_id}] Rule-ranked {len(jobs)} jobs and selected "
            f"top {len(selected_jobs)} jobs for matching"
        )

        with _lock:
            _match_runs[run_id]["total"] = len(selected_jobs)
            _match_runs[run_id]["candidate_pool"] = len(jobs)
            _match_runs[run_id]["message"] = f"Selected top {len(selected_jobs)} jobs after rule-based ranking"

        if not selected_jobs:
            with _lock:
                _match_runs[run_id]["status"] = "completed"
                _match_runs[run_id]["matched"] = 0
                _match_runs[run_id]["finished_at"] = datetime.now(tz=timezone.utc).isoformat()
                _match_runs[run_id]["message"] = "No described jobs available for matching"
            return

        matched = 0
        ai_budget_available = use_ai
        for job in selected_jobs:
            description = job.get("description", "") or ""
            fast_result = job["_fast_result"]
            parsed_jd = job["_parsed_jd_local"]
            final_score = fast_result["total_score"]
            strengths = fast_result["strengths"]
            gaps = fast_result["gaps"]
            cover_letter_angles = []
            fit_tier = fast_result["fit_tier"]

            if ai_budget_available and fast_result["total_score"] >= ai_threshold:
                try:
                    parsed_jd = parse_jd(
                        description,
                        title=job.get("title", ""),
                        company=job.get("company", ""),
                    )
                    ai_result = match_resume_ai(
                        parsed_jd,
                        job_title=job.get("title", ""),
                        company=job.get("company", ""),
                    )
                    final_score = ai_result.get("total_score", fast_result["total_score"])
                    strengths = ai_result.get("strengths", fast_result["strengths"])
                    gaps = ai_result.get("gaps", fast_result["gaps"])
                    cover_letter_angles = ai_result.get("cover_letter_angles", [])
                    fit_tier = ai_result.get("fit_tier", fast_result["fit_tier"])
                except Exception as exc:
                    logger.warning(
                        f"[match:{run_id}] AI JD parse failed for "
                        f"{job.get('title', '')} @ {job.get('company', '')}: {exc}. "
                        "Falling back to rule-based matching for the rest of this run."
                    )
                    ai_budget_available = False

            h1b_score = float(job.get("h1b_score") or 0)
            combined = round(final_score * 0.6 + h1b_score * 0.4, 1)

            ops.upsert_match_result({
                "job_hash": job["job_hash"],
                "match_score": final_score,
                "h1b_score": h1b_score,
                "combined_score": combined,
                "fit_tier": fit_tier,
                "strengths": strengths,
                "gaps": gaps,
                "cover_letter_angles": cover_letter_angles,
            })
            matched += 1
            with _lock:
                _match_runs[run_id]["matched"] = matched
                if ai_budget_available and use_ai:
                    _match_runs[run_id]["message"] = "AI matching strongest shortlisted jobs"
                else:
                    _match_runs[run_id]["message"] = "Rule-based matching shortlisted jobs"

        with _lock:
            _match_runs[run_id]["status"] = "completed"
            _match_runs[run_id]["matched"] = matched
            _match_runs[run_id]["finished_at"] = datetime.now(tz=timezone.utc).isoformat()
            _match_runs[run_id]["message"] = f"Matched {matched} shortlisted jobs"

        logger.info(f"[match:{run_id}] Matched {matched} jobs")

    except Exception as exc:
        logger.exception(f"[match:{run_id}] Matching failed")
        with _lock:
            _match_runs[run_id]["status"] = "failed"
            _match_runs[run_id]["error"] = str(exc)
            _match_runs[run_id]["finished_at"] = datetime.now(tz=timezone.utc).isoformat()


@router.post("/run", response_model=MatchRunResponse, status_code=202)
def run_match(body: MatchRunRequest, background_tasks: BackgroundTasks):
    """
    Trigger resume-JD matching for unmatched jobs.
    Returns immediately; poll /match/runs/{run_id} for status.
    """
    run_id = str(uuid.uuid4())[:8]
    with _lock:
            _match_runs[run_id] = {
                "run_id": run_id,
                "status": "pending",
                "started_at": None,
                "finished_at": None,
                "matched": 0,
                "total": 0,
                "message": f"Queued top-{body.limit}-job rule ranking",
                "error": None,
            }

    background_tasks.add_task(
        _run_matching, run_id, body.limit, body.use_ai, body.ai_threshold
    )

    return MatchRunResponse(
        run_id=run_id,
        status="pending",
        message=f"Matching queued for the top {body.limit} jobs — poll /match/runs/{run_id}",
    )


@router.get("/runs/{run_id}")
def get_match_run(run_id: str):
    with _lock:
        run = _match_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/results")
def get_match_results(
    min_combined: float = Query(0.0, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: PGConnection = Depends(get_db),
):
    """
    Return match results joined with job info, ordered by combined score.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                mr.*,
                j.title, j.company, j.location, j.source, j.url,
                j.salary_min, j.salary_max, j.status, j.sponsors_h1b,
                j.h1b_filings, j.h1b_avg_salary
            FROM match_results mr
            JOIN jobs j ON j.job_hash = mr.job_hash
            WHERE mr.combined_score >= %s
            ORDER BY mr.combined_score DESC
            LIMIT %s OFFSET %s
            """,
            (min_combined, limit, offset),
        )
        rows = cur.fetchall()

    return [dict(r) for r in rows]
