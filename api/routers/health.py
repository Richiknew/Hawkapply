"""
Health check endpoint — no auth required.
"""

from fastapi import APIRouter, Depends
from psycopg2.extensions import connection as PGConnection

from api.dependencies import get_db

router = APIRouter()


@router.get("/health", tags=["health"])
def health_check(conn: PGConnection = Depends(get_db)):
    """Returns service status and DB connectivity."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
        "service": "hawkapply-api",
    }
