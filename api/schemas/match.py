from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class MatchResultOut(BaseModel):
    id: int
    job_hash: str
    match_score: Optional[float]
    h1b_score: Optional[float]
    combined_score: Optional[float]
    fit_tier: Optional[str]
    parsed_jd: Optional[dict[str, Any]]
    strengths: Optional[list[str]]
    gaps: Optional[list[str]]
    cover_letter_angles: Optional[list[str]]
    matched_at: datetime

    model_config = {"from_attributes": True}


class MatchRunRequest(BaseModel):
    limit: int = 100
    use_ai: bool = False
    ai_threshold: float = 60.0


class MatchRunResponse(BaseModel):
    run_id: str
    status: str
    message: str


class JobWithMatch(BaseModel):
    job: dict[str, Any]
    match: Optional[dict[str, Any]]
