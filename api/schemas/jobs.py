from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl


class JobOut(BaseModel):
    id: int
    job_hash: str
    title: str
    company: str
    location: str
    source: str
    url: str
    description: str
    salary_min: Optional[int]
    salary_max: Optional[int]
    posted_date: Optional[datetime]
    scraped_at: datetime
    h1b_filings: int
    h1b_avg_salary: Optional[int]
    sponsors_h1b: Optional[bool]
    h1b_score: float
    status: str
    applied_at: Optional[datetime]
    notes: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobUpdate(BaseModel):
    status: Optional[str] = None  # new | reviewing | applied | interview | rejected | offer
    notes: Optional[str] = None


class JobListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobOut]
