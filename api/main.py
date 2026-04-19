"""
HawkApply — FastAPI application entry point.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from api.dependencies import close_pool, init_pool
from api.routers import health, jobs, match, pipeline, resume, stats
from config import settings

# ── Logging ──────────────────────────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
    level="INFO",
)
logger.add(
    "logs/api.log",
    rotation="10 MB",
    retention="14 days",
    compression="gz",
    level="DEBUG",
    enqueue=True,
)


# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    yield
    close_pool()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="HawkApply API",
    description="AI-powered H1B job application pipeline",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# In production, restrict origins to your actual dashboard domain.
ALLOWED_ORIGINS = [
    "http://localhost:3000",   # Next.js dev
    "http://localhost:5173",   # Vite dev
    *([settings.DASHBOARD_URL] if settings.DASHBOARD_URL else []),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ── Request logging middleware ────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    logger.info(f"{request.method} {request.url.path} → {response.status_code}")
    return response


# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(jobs.router,     prefix="/jobs",     tags=["jobs"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])
app.include_router(match.router,    prefix="/match",    tags=["match"])
app.include_router(resume.router,   prefix="/resume",   tags=["resume"])
app.include_router(stats.router,    prefix="/stats",    tags=["stats"])
