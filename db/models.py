"""
Data models for HawkApply.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib


@dataclass
class Job:
    """Represents a scraped job posting."""

    title: str
    company: str
    location: str
    source: str  # "indeed", "linkedin", "glassdoor"
    url: str
    description: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    posted_date: Optional[datetime] = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    # H1B enrichment (filled by h1b_matcher)
    h1b_filings: int = 0
    h1b_avg_salary: Optional[int] = None
    sponsors_h1b: Optional[bool] = None

    # Scoring (filled by scorer)
    h1b_score: float = 0.0  # 0-100

    # Application tracking (Phase 3+)
    status: str = "new"  # new, reviewing, applied, interview, rejected, offer

    # Deduplication
    job_hash: str = ""

    def __post_init__(self):
        if not self.job_hash:
            self.job_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Unique hash based on company + title + location."""
        raw = f"{self.company.lower().strip()}|{self.title.lower().strip()}|{self.location.lower().strip()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @property
    def salary_display(self) -> str:
        if self.salary_min and self.salary_max:
            return f"${self.salary_min:,} - ${self.salary_max:,}"
        elif self.salary_min:
            return f"${self.salary_min:,}+"
        elif self.salary_max:
            return f"Up to ${self.salary_max:,}"
        elif self.h1b_avg_salary:
            return f"~${self.h1b_avg_salary:,} (H1B avg)"
        return "Not listed"

    @property
    def sponsorship_display(self) -> str:
        if self.sponsors_h1b is True:
            return f"✅ Yes ({self.h1b_filings} filings)"
        elif self.sponsors_h1b is False:
            return "❌ No history"
        return "❓ Unknown"


@dataclass
class H1BSponsor:
    """H1B sponsorship data for a company."""

    company_name: str
    normalized_name: str  # lowercase, stripped
    total_filings: int = 0
    data_scientist_filings: int = 0
    avg_salary: int = 0
    approval_rate: float = 0.0
    last_filing_year: int = 0

    def __post_init__(self):
        if not self.normalized_name:
            self.normalized_name = self._normalize(self.company_name)

    @staticmethod
    def _normalize(name: str) -> str:
        """Normalize company name for fuzzy matching."""
        name = name.lower().strip()
        # Remove common suffixes
        for suffix in [
            ", inc.", ", inc", " inc.", " inc",
            ", llc", " llc", ", ltd", " ltd",
            " corporation", " corp.", " corp",
            " company", " co.", " co",
            " technologies", " technology",
            " solutions", " services",
            " group", " holdings",
        ]:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        return name.strip()
