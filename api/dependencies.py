"""
Shared FastAPI dependencies: DB connection pool, API key auth.
"""

from __future__ import annotations

import psycopg2
import psycopg2.pool
import psycopg2.extras
from fastapi import Header, HTTPException, status
from loguru import logger

from config import settings

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        dsn=settings.DATABASE_URL,
    )
    logger.info("DB connection pool ready (min=2 max=10)")


def close_pool() -> None:
    global _pool
    if _pool:
        _pool.closeall()
        logger.info("DB connection pool closed")


def _fresh_connection():
    """Get a validated connection from the pool, replacing stale ones if needed."""
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() first")

    conn = _pool.getconn()
    try:
        if conn.closed:
            _pool.putconn(conn, close=True)
            conn = _pool.getconn()

        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return conn
    except Exception:
        try:
            _pool.putconn(conn, close=True)
        except Exception:
            pass
        conn = _pool.getconn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return conn


def get_db():
    """Yield a psycopg2 connection from the pool; return it on exit."""
    conn = _fresh_connection()
    try:
        yield conn
    except Exception:
        if not conn.closed:
            conn.rollback()
        raise
    finally:
        if _pool is None:
            return
        if conn.closed:
            _pool.putconn(conn, close=True)
        else:
            _pool.putconn(conn)


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Validate the X-API-Key header against the configured secret."""
    if not settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API_KEY not configured on server",
        )
    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
