from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    refresh_h1b: bool = False


class PipelineFilters(BaseModel):
    """Snapshot of scraping filters active at pipeline run time."""
    target_roles: list[str] = []
    locations: list[str] = []
    min_salary: int = 0
    posted_within_days: int = Field(default=2, ge=1, le=7)
    min_h1b_filings: int = 0
    require_sponsorship: bool = False
    company_count: int = 0


class PipelineConfigUpdate(BaseModel):
    target_roles: list[str]
    locations: list[str]
    min_salary: int
    posted_within_days: int = Field(ge=1, le=7)
    min_h1b_filings: int
    require_sponsorship: bool


class PipelineStatus(BaseModel):
    run_id: str
    status: str          # pending | running | completed | failed
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    jobs_scraped: int = 0
    jobs_matched: int = 0
    error: Optional[str] = None
    message: str = ""
    filters: Optional[PipelineFilters] = None


class PipelineRunResponse(BaseModel):
    run_id: str
    status: str
    message: str
