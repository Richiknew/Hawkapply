"""
H1B Job Scoring Engine — ranks jobs by H1B-friendliness.

Score = 0-100 based on:
  - Company H1B filing history (40 pts)
  - Salary competitiveness (30 pts)
  - Sponsorship signals in job text (20 pts)
  - Recency of filings (10 pts)
"""

from typing import Optional


def compute_h1b_score(
    h1b_filings: int = 0,
    avg_salary: int = 0,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    sponsors_signal: Optional[bool] = None,
    last_filing_year: int = 2025,
) -> float:
    """
    Compute a 0-100 H1B-friendliness score for a job.

    Weights:
        Filing history:  40 points
        Salary level:    30 points
        Text signals:    20 points
        Recency:         10 points
    """
    score = 0.0

    # ---- 1. Filing History (40 pts) ----
    # More filings = more likely to sponsor your specific role
    if h1b_filings >= 100:
        score += 40
    elif h1b_filings >= 50:
        score += 35
    elif h1b_filings >= 20:
        score += 28
    elif h1b_filings >= 10:
        score += 20
    elif h1b_filings >= 5:
        score += 12
    elif h1b_filings >= 1:
        score += 5

    # ---- 2. Salary (30 pts) ----
    # Higher salary = better H1B lottery odds under the new wage-based system
    effective_salary = salary_min or salary_max or avg_salary or 0

    if effective_salary >= 200000:
        score += 30
    elif effective_salary >= 170000:
        score += 27
    elif effective_salary >= 150000:
        score += 24
    elif effective_salary >= 130000:
        score += 20
    elif effective_salary >= 110000:
        score += 12
    elif effective_salary >= 90000:
        score += 6

    # ---- 3. Sponsorship Signals (20 pts) ----
    if sponsors_signal is True:
        score += 20  # Explicitly mentioned in job posting
    elif sponsors_signal is None:
        score += 5   # No mention either way — neutral
    # sponsors_signal == False → 0 points (explicitly says no)

    # ---- 4. Recency (10 pts) ----
    if last_filing_year >= 2025:
        score += 10
    elif last_filing_year >= 2024:
        score += 7
    elif last_filing_year >= 2023:
        score += 4

    return round(min(score, 100), 1)


def score_tier(score: float) -> str:
    """Convert numeric score to a human-readable tier."""
    if score >= 80:
        return "🟢 Excellent"
    elif score >= 60:
        return "🔵 Strong"
    elif score >= 40:
        return "🟡 Moderate"
    elif score >= 20:
        return "🟠 Low"
    return "🔴 Unlikely"
