"""
Database operations — insert, query, update jobs and sponsors.
"""

import psycopg2
import psycopg2.extras
from typing import Optional
from config import settings
from db.models import Job, H1BSponsor


def get_connection():
    """Get a database connection."""
    return psycopg2.connect(settings.DATABASE_URL)


# --------------- Jobs ---------------

def upsert_job(job: Job) -> bool:
    """
    Insert a job or skip if it already exists (based on job_hash).
    Returns True if inserted, False if duplicate.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO jobs (
                    job_hash, title, company, location, source, url,
                    description, salary_min, salary_max, posted_date, scraped_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_hash) DO UPDATE SET
                    description = EXCLUDED.description,
                    salary_min = COALESCE(EXCLUDED.salary_min, jobs.salary_min),
                    salary_max = COALESCE(EXCLUDED.salary_max, jobs.salary_max),
                    updated_at = NOW()
                RETURNING id;
            """, (
                job.job_hash, job.title, job.company, job.location,
                job.source, job.url, job.description,
                job.salary_min, job.salary_max,
                job.posted_date, job.scraped_at,
            ))
            result = cur.fetchone()
            conn.commit()
            return result is not None
    finally:
        conn.close()


def upsert_jobs_batch(jobs: list[Job]) -> int:
    """Insert multiple jobs. Returns count of new jobs."""
    conn = get_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for job in jobs:
                cur.execute("""
                    INSERT INTO jobs (
                        job_hash, title, company, location, source, url,
                        description, salary_min, salary_max, posted_date, scraped_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (job_hash) DO NOTHING
                    RETURNING id;
                """, (
                    job.job_hash, job.title, job.company, job.location,
                    job.source, job.url, job.description,
                    job.salary_min, job.salary_max,
                    job.posted_date, job.scraped_at,
                ))
                if cur.fetchone():
                    inserted += 1
            conn.commit()
    finally:
        conn.close()
    return inserted


def get_jobs(
    status: Optional[str] = None,
    min_score: float = 0.0,
    min_salary: Optional[int] = None,
    sponsors_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Query jobs with filters."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            conditions = ["1=1"]
            params: list = []

            if status:
                conditions.append("status = %s")
                params.append(status)
            if min_score > 0:
                conditions.append("h1b_score >= %s")
                params.append(min_score)
            if min_salary:
                conditions.append("(salary_min >= %s OR h1b_avg_salary >= %s)")
                params.extend([min_salary, min_salary])
            if sponsors_only:
                conditions.append("sponsors_h1b = TRUE")

            where = " AND ".join(conditions)
            params.extend([limit, offset])

            cur.execute(f"""
                SELECT * FROM jobs
                WHERE {where}
                ORDER BY h1b_score DESC, salary_min DESC NULLS LAST, scraped_at DESC
                LIMIT %s OFFSET %s;
            """, params)
            return cur.fetchall()
    finally:
        conn.close()


def update_job_h1b(job_hash: str, h1b_filings: int, h1b_avg_salary: int,
                   sponsors_h1b: bool, h1b_score: float):
    """Update a job's H1B enrichment data."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs SET
                    h1b_filings = %s,
                    h1b_avg_salary = %s,
                    sponsors_h1b = %s,
                    h1b_score = %s,
                    updated_at = NOW()
                WHERE job_hash = %s;
            """, (h1b_filings, h1b_avg_salary, sponsors_h1b, h1b_score, job_hash))
            conn.commit()
    finally:
        conn.close()


def update_job_status(job_hash: str, status: str, notes: str = ""):
    """Update application status."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE jobs SET
                    status = %s,
                    notes = %s,
                    applied_at = CASE WHEN %s = 'applied' THEN NOW() ELSE applied_at END,
                    updated_at = NOW()
                WHERE job_hash = %s;
            """, (status, notes, status, job_hash))
            conn.commit()
    finally:
        conn.close()


def get_job_stats() -> dict:
    """Get summary statistics."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total_jobs,
                    COUNT(*) FILTER (WHERE sponsors_h1b = TRUE) as sponsoring_jobs,
                    COUNT(*) FILTER (WHERE salary_min >= 130000) as high_salary_jobs,
                    COUNT(*) FILTER (WHERE status = 'new') as new_jobs,
                    COUNT(*) FILTER (WHERE status = 'applied') as applied_jobs,
                    ROUND(AVG(h1b_score)::numeric, 1) as avg_score,
                    COUNT(DISTINCT company) as unique_companies
                FROM jobs;
            """)
            return cur.fetchone()
    finally:
        conn.close()


# --------------- H1B Sponsors ---------------

def upsert_sponsor(sponsor: H1BSponsor):
    """Insert or update H1B sponsor data."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO h1b_sponsors (
                    company_name, normalized_name, total_filings,
                    data_scientist_filings, avg_salary, approval_rate, last_filing_year
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (normalized_name) DO UPDATE SET
                    total_filings = EXCLUDED.total_filings,
                    data_scientist_filings = EXCLUDED.data_scientist_filings,
                    avg_salary = EXCLUDED.avg_salary,
                    approval_rate = EXCLUDED.approval_rate,
                    last_filing_year = EXCLUDED.last_filing_year,
                    updated_at = NOW();
            """, (
                sponsor.company_name, sponsor.normalized_name,
                sponsor.total_filings, sponsor.data_scientist_filings,
                sponsor.avg_salary, sponsor.approval_rate, sponsor.last_filing_year,
            ))
            conn.commit()
    finally:
        conn.close()


def find_sponsor(company_name: str) -> Optional[dict]:
    """Look up a company in the H1B sponsors table using fuzzy matching."""
    normalized = H1BSponsor._normalize(company_name)
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Exact match first
            cur.execute(
                "SELECT * FROM h1b_sponsors WHERE normalized_name = %s;",
                (normalized,)
            )
            result = cur.fetchone()
            if result:
                return result

            # Partial match (company name contains or is contained by)
            cur.execute("""
                SELECT * FROM h1b_sponsors
                WHERE normalized_name LIKE %s OR %s LIKE '%%' || normalized_name || '%%'
                ORDER BY total_filings DESC
                LIMIT 1;
            """, (f"%{normalized}%", normalized))
            return cur.fetchone()
    finally:
        conn.close()


def get_all_sponsors() -> list[dict]:
    """Get all cached H1B sponsors."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM h1b_sponsors ORDER BY total_filings DESC;")
            return cur.fetchall()
    finally:
        conn.close()
