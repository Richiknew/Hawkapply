"""
HawkApply configuration — loads env defaults and optional persisted pipeline overrides.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


def _csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_posted_within_days(value: Any, fallback: int = 2) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return fallback
    return days if 1 <= days <= 7 else fallback


class Settings:
    def __init__(self) -> None:
        # Paths
        self.PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
        self.DATA_DIR: Path = self.PROJECT_ROOT / "data"
        self.PIPELINE_CONFIG_PATH: Path = self.DATA_DIR / "pipeline_config.json"

        # Database
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql://localhost:5432/hawkapply",
        )

        # Pipeline defaults from env
        self._default_target_roles: list[str] = _csv_list(
            os.getenv("TARGET_ROLE", "data scientist")
        )
        self._default_min_salary: int = int(os.getenv("MIN_SALARY", "130000"))
        self._default_posted_within_days: int = _normalize_posted_within_days(
            os.getenv("POSTED_WITHIN_DAYS", "2")
        )
        self._default_locations: list[str] = _csv_list(
            os.getenv(
                "LOCATIONS",
                "New York,San Francisco,Seattle,Boston,Chicago,Austin,Remote,"
                "Washington DC,Philadelphia,Atlanta,Charlotte,Raleigh,Newark,"
                "Jersey City,Stamford,Pittsburgh,Baltimore,Miami,Tampa,"
                "Dallas,Houston,Denver,Minneapolis,Detroit,San Jose,"
                "Los Angeles,San Diego,Portland,Phoenix,Salt Lake City",
            )
        )
        self._default_require_sponsorship: bool = (
            os.getenv("REQUIRE_SPONSORSHIP", "true").lower() == "true"
        )
        self._default_min_h1b_filings: int = int(os.getenv("MIN_H1B_FILINGS", "5"))

        # Scraping
        self.REQUEST_DELAY: float = 2.0
        self.USER_AGENT: str = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
        self.MAX_PAGES_PER_SEARCH: int = 5

        # Job APIs
        self.RAPIDAPI_KEY: str = os.getenv("RAPIDAPI_KEY", "")
        self.ADZUNA_APP_ID: str = os.getenv("ADZUNA_APP_ID", "")
        self.ADZUNA_APP_KEY: str = os.getenv("ADZUNA_APP_KEY", "")

        # LLM APIs
        self.ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

        # API server
        self.API_KEY: str = os.getenv("API_KEY", "")
        self.DASHBOARD_URL: str = os.getenv("DASHBOARD_URL", "")

    def _pipeline_defaults(self) -> dict[str, Any]:
        return {
            "target_roles": list(self._default_target_roles),
            "locations": list(self._default_locations),
            "min_salary": self._default_min_salary,
            "posted_within_days": self._default_posted_within_days,
            "min_h1b_filings": self._default_min_h1b_filings,
            "require_sponsorship": self._default_require_sponsorship,
        }

    def _read_pipeline_overrides(self) -> dict[str, Any]:
        if not self.PIPELINE_CONFIG_PATH.exists():
            return {}
        try:
            return json.loads(self.PIPELINE_CONFIG_PATH.read_text())
        except Exception:
            return {}

    def get_pipeline_config(self) -> dict[str, Any]:
        config = self._pipeline_defaults()
        overrides = self._read_pipeline_overrides()

        target_roles = overrides.get("target_roles")
        if isinstance(target_roles, list):
            config["target_roles"] = [str(item).strip() for item in target_roles if str(item).strip()]

        locations = overrides.get("locations")
        if isinstance(locations, list):
            config["locations"] = [str(item).strip() for item in locations if str(item).strip()]

        min_salary = overrides.get("min_salary")
        if isinstance(min_salary, int):
            config["min_salary"] = max(min_salary, 0)

        posted_within_days = overrides.get("posted_within_days")
        if isinstance(posted_within_days, int):
            config["posted_within_days"] = _normalize_posted_within_days(
                posted_within_days,
                fallback=self._default_posted_within_days,
            )

        min_h1b_filings = overrides.get("min_h1b_filings")
        if isinstance(min_h1b_filings, int):
            config["min_h1b_filings"] = max(min_h1b_filings, 0)

        require_sponsorship = overrides.get("require_sponsorship")
        if isinstance(require_sponsorship, bool):
            config["require_sponsorship"] = require_sponsorship

        return config

    def save_pipeline_config(
        self,
        *,
        target_roles: list[str],
        locations: list[str],
        min_salary: int,
        posted_within_days: int,
        min_h1b_filings: int,
        require_sponsorship: bool,
    ) -> dict[str, Any]:
        config = {
            "target_roles": [item.strip() for item in target_roles if item.strip()],
            "locations": [item.strip() for item in locations if item.strip()],
            "min_salary": max(int(min_salary), 0),
            "posted_within_days": _normalize_posted_within_days(
                posted_within_days,
                fallback=self._default_posted_within_days,
            ),
            "min_h1b_filings": max(int(min_h1b_filings), 0),
            "require_sponsorship": bool(require_sponsorship),
        }

        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.PIPELINE_CONFIG_PATH.write_text(json.dumps(config, indent=2))
        return self.get_pipeline_config()

    @property
    def TARGET_ROLES(self) -> list[str]:
        return self.get_pipeline_config()["target_roles"]

    @property
    def MIN_SALARY(self) -> int:
        return self.get_pipeline_config()["min_salary"]

    @property
    def LOCATIONS(self) -> list[str]:
        return self.get_pipeline_config()["locations"]

    @property
    def POSTED_WITHIN_DAYS(self) -> int:
        return self.get_pipeline_config()["posted_within_days"]

    @property
    def REQUIRE_SPONSORSHIP(self) -> bool:
        return self.get_pipeline_config()["require_sponsorship"]

    @property
    def MIN_H1B_FILINGS(self) -> int:
        return self.get_pipeline_config()["min_h1b_filings"]


settings = Settings()
