"""
HawkApply configuration — loads from .env and provides defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://localhost:5432/hawkapply"
    )

    # Job search
    TARGET_ROLES: list[str] = [
        r.strip()
        for r in os.getenv("TARGET_ROLE", "data scientist").split(",")
    ]
    MIN_SALARY: int = int(os.getenv("MIN_SALARY", "130000"))
    LOCATIONS: list[str] = [
        loc.strip()
        for loc in os.getenv(
            "LOCATIONS",
            "New York,San Francisco,Seattle,Boston,Chicago,Austin,Remote,"
            "Washington DC,Philadelphia,Atlanta,Charlotte,Raleigh,Newark,"
            "Jersey City,Stamford,Pittsburgh,Baltimore,Miami,Tampa,"
            "Dallas,Houston,Denver,Minneapolis,Detroit,San Jose,"
            "Los Angeles,San Diego,Portland,Phoenix,Salt Lake City"
        ).split(",")
    ]

    # H1B
    REQUIRE_SPONSORSHIP: bool = os.getenv("REQUIRE_SPONSORSHIP", "true").lower() == "true"
    MIN_H1B_FILINGS: int = int(os.getenv("MIN_H1B_FILINGS", "5"))

    # Scraping
    REQUEST_DELAY: float = 2.0  # seconds between requests (be polite)
    USER_AGENT: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    MAX_PAGES_PER_SEARCH: int = 5  # pages per search query
    # Job APIs (free tiers)
    RAPIDAPI_KEY: str = os.getenv("RAPIDAPI_KEY", "")
    ADZUNA_APP_ID: str = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY: str = os.getenv("ADZUNA_APP_KEY", "")
    # Anthropic (Phase 2)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Paths
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data"


settings = Settings()
