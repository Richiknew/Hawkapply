"""
Stats endpoint — aggregate numbers for the dashboard.
"""

from __future__ import annotations

import psycopg2.extras
from fastapi import APIRouter, Depends
from psycopg2.extensions import connection as PGConnection

from api.dependencies import get_db, verify_api_key
from config import settings

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("")
def get_stats(conn: PGConnection = Depends(get_db)):
    """Aggregate job stats for the dashboard."""
    min_salary = settings.MIN_SALARY
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT
                COUNT(*)                                             AS total_jobs,
                COUNT(*) FILTER (WHERE sponsors_h1b = TRUE)         AS sponsoring_jobs,
                COUNT(*) FILTER (
                    WHERE COALESCE(salary_min, salary_max, h1b_avg_salary) >= %s
                )                                                    AS high_salary_jobs,
                COUNT(*) FILTER (WHERE status = 'new')              AS new_jobs,
                COUNT(*) FILTER (WHERE status = 'reviewing')        AS reviewing_jobs,
                COUNT(*) FILTER (WHERE status = 'applied')          AS applied_jobs,
                COUNT(*) FILTER (WHERE status = 'interview')        AS interview_jobs,
                COUNT(*) FILTER (WHERE status = 'offer')            AS offer_jobs,
                COUNT(*) FILTER (WHERE status = 'rejected')         AS rejected_jobs,
                ROUND(AVG(h1b_score)::numeric, 1)                   AS avg_h1b_score,
                COUNT(DISTINCT company)                             AS unique_companies,
                MAX(scraped_at)                                     AS last_scraped_at
            FROM jobs;
        """, (min_salary,))
        jobs_stats = dict(cur.fetchone())

        cur.execute("""
            SELECT
                COUNT(*)                        AS total_matched,
                ROUND(AVG(combined_score)::numeric, 1) AS avg_combined_score,
                COUNT(*) FILTER (WHERE fit_tier LIKE '%Strong%') AS strong_matches,
                COUNT(*) FILTER (WHERE fit_tier LIKE '%Good%')   AS good_matches,
                COUNT(*) FILTER (WHERE fit_tier LIKE '%Stretch%') AS stretch_matches
            FROM match_results;
        """)
        match_stats = dict(cur.fetchone())

        cur.execute("""
            SELECT source, COUNT(*) AS count
            FROM jobs
            GROUP BY source
            ORDER BY count DESC;
        """)
        by_source = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT
                CASE
                    WHEN h1b_score >= 80 THEN 'Excellent (80+)'
                    WHEN h1b_score >= 60 THEN 'Strong (60-79)'
                    WHEN h1b_score >= 40 THEN 'Moderate (40-59)'
                    WHEN h1b_score >= 20 THEN 'Low (20-39)'
                    ELSE 'Unlikely (<20)'
                END AS tier,
                COUNT(*) AS count
            FROM jobs
            GROUP BY tier
            ORDER BY MIN(h1b_score) DESC;
        """)
        by_h1b_tier = [dict(r) for r in cur.fetchall()]

    return {
        "jobs": jobs_stats,
        "match": match_stats,
        "by_source": by_source,
        "by_h1b_tier": by_h1b_tier,
        "config": {
            "min_salary": min_salary,
        },
    }
