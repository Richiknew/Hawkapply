"""
Job endpoints — list, get, update status/notes, lookup by URL, save from extension.
"""

from __future__ import annotations

import hashlib
from typing import Optional
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg2.extensions import connection as PGConnection
from pydantic import BaseModel

from api.dependencies import get_db, verify_api_key
from api.schemas.jobs import JobListResponse, JobOut, JobUpdate

router = APIRouter(dependencies=[Depends(verify_api_key)])

VALID_STATUSES = {"new", "reviewing", "applied", "interview", "rejected", "offer"}


@router.get("", response_model=JobListResponse)
def list_jobs(
    job_status: Optional[str] = Query(None, alias="status"),
    min_score: float = Query(0.0, ge=0, le=100),
    min_salary: Optional[int] = Query(None, ge=0),
    sponsors_only: bool = Query(False),
    sponsor: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description="Filter by source (e.g. career_page, jsearch)"),
    location: Optional[str] = Query(None, description="Filter by location substring"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: PGConnection = Depends(get_db),
):
    """List jobs with optional filters. Ordered by H1B score then salary."""
    conditions = ["1=1"]
    params: list = []

    if job_status:
        if job_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"status must be one of {sorted(VALID_STATUSES)}",
            )
        conditions.append("j.status = %s")
        params.append(job_status)
    if min_score > 0:
        conditions.append("j.h1b_score >= %s")
        params.append(min_score)
    if min_salary:
        conditions.append("(j.salary_min >= %s OR j.h1b_avg_salary >= %s)")
        params.extend([min_salary, min_salary])
    if sponsor is True:
        sponsors_only = True
    if sponsors_only:
        conditions.append("j.sponsors_h1b = TRUE")
    elif sponsor is False:
        conditions.append("COALESCE(j.sponsors_h1b, FALSE) = FALSE")
    if search:
        conditions.append("(j.title ILIKE %s OR j.company ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if source:
        conditions.append("j.source = %s")
        params.append(source)
    if location:
        conditions.append("j.location ILIKE %s")
        params.append(f"%{location}%")

    where = " AND ".join(conditions)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT COUNT(*) FROM jobs j WHERE {where}", params)
        total = cur.fetchone()["count"]

        cur.execute(
            f"""
            SELECT j.*
            FROM jobs j
            WHERE {where}
            ORDER BY j.h1b_score DESC, j.salary_min DESC NULLS LAST, j.scraped_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall()

    return JobListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[JobOut(**dict(r)) for r in rows],
    )


class JobFromExtension(BaseModel):
    title: str
    company: str
    location: str = ""
    url: str
    description: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    source: str = "extension"


@router.get("/lookup", response_model=Optional[JobOut])
def lookup_job_by_url(
    url: str = Query(...),
    conn: PGConnection = Depends(get_db),
):
    """Look up a job by URL (strips query params for fuzzy matching). Returns null if not found."""
    # Strip query params so linkedin/greenhouse tracking params don't break matching
    base_url = url.split("?")[0].rstrip("/")
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM jobs WHERE split_part(url, '?', 1) = %s LIMIT 1",
            (base_url,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return JobOut(**dict(row))


@router.post("", response_model=JobOut, status_code=201)
def save_job_from_extension(
    body: JobFromExtension,
    conn: PGConnection = Depends(get_db),
):
    """Save a job discovered via the browser extension."""
    raw = f"{body.company.lower().strip()}|{body.title.lower().strip()}|{body.location.lower().strip()}"
    job_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Upsert — if same hash exists, just return it
        cur.execute(
            """
            INSERT INTO jobs (job_hash, title, company, location, url, description,
                              salary_min, salary_max, source, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'new')
            ON CONFLICT (job_hash) DO UPDATE
                SET updated_at = NOW()
            RETURNING *
            """,
            (
                job_hash,
                body.title,
                body.company,
                body.location,
                body.url,
                body.description,
                body.salary_min,
                body.salary_max,
                body.source,
            ),
        )
        row = cur.fetchone()
        conn.commit()
    return JobOut(**dict(row))


@router.get("/{job_hash}", response_model=JobOut)
def get_job(job_hash: str, conn: PGConnection = Depends(get_db)):
    """Fetch a single job by its hash."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM jobs WHERE job_hash = %s", (job_hash,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut(**dict(row))


@router.patch("/{job_hash}", response_model=JobOut)
def update_job(
    job_hash: str,
    body: JobUpdate,
    conn: PGConnection = Depends(get_db),
):
    """Update a job's status and/or notes."""
    if body.status and body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of {sorted(VALID_STATUSES)}",
        )

    set_clauses = ["updated_at = NOW()"]
    params: list = []

    if body.status is not None:
        set_clauses.append("status = %s")
        params.append(body.status)
        if body.status == "applied":
            set_clauses.append("applied_at = NOW()")

    if body.notes is not None:
        set_clauses.append("notes = %s")
        params.append(body.notes)

    params.append(job_hash)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"UPDATE jobs SET {', '.join(set_clauses)} WHERE job_hash = %s RETURNING *",
            params,
        )
        row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut(**dict(row))


@router.get("/{job_hash}/match")
def get_job_match(job_hash: str, conn: PGConnection = Depends(get_db)):
    """Get the match result for a specific job (if it has been matched)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM match_results WHERE job_hash = %s",
            (job_hash,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No match result for this job")
    return dict(row)


@router.get("/{job_hash}/autofill")
def get_job_autofill(job_hash: str, conn: PGConnection = Depends(get_db)):
    """Return extension-friendly autofill data for a specific job."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM jobs WHERE job_hash = %s", (job_hash,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        from autofill import export_autofill, get_match_data
        from parsers.resume_parser import load_profile, profile_exists
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Autofill not available: {exc}") from exc

    if not profile_exists():
        raise HTTPException(
            status_code=404,
            detail="No candidate profile found. Upload or parse your resume first.",
        )

    profile = load_profile()
    job = dict(row)
    match_data = get_match_data(job_hash)
    payload = export_autofill(
        profile,
        job=job,
        match_data=match_data,
        include_custom_answers=False,
    )
    return payload
