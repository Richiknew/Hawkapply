"""
Multi-source job scraper using FREE APIs.

Sources:
  1. JSearch (RapidAPI) — aggregates Google for Jobs (LinkedIn, Indeed, Glassdoor, etc.)
     Free tier: 200 requests/month
  2. Adzuna API — free with registration, 250 requests/day
  3. LinkedIn public job RSS — no auth needed
  4. RemoteOK API — no auth needed (for remote jobs)

Why not scrape Indeed/LinkedIn directly?
  → They block requests with 403s. These APIs aggregate the same data legally.

Usage:
    python -m scrapers.job_scraper
"""

import re
import time
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional
from config import settings
from db.models import Job
from scrapers.indeed_scraper import detect_sponsorship, parse_salary


# ──────────────────────────────────────────────────
# Source 1: JSearch API (Google for Jobs aggregator)
# ──────────────────────────────────────────────────
# Free tier: 200 requests/month on RapidAPI
# Sign up: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch

def scrape_jsearch(
    query: str = "data scientist visa sponsorship",
    location: str = "New York, NY",
    pages: int = 2,
    api_key: str = "",
) -> list[Job]:
    """Scrape jobs via JSearch API (RapidAPI)."""

    if not api_key:
        api_key = settings.RAPIDAPI_KEY
    if not api_key:
        print("  ⚠️  No RAPIDAPI_KEY set — skipping JSearch")
        return []

    jobs = []
    session = requests.Session()
    session.headers.update({
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
    })

    for page in range(1, pages + 1):
        print(f"  📡 JSearch page {page}/{pages}: '{query}' in {location}...")

        try:
            resp = session.get(
                "https://jsearch.p.rapidapi.com/search",
                params={
                    "query": f"{query} in {location}",
                    "page": str(page),
                    "num_pages": "1",
                    "date_posted": "week",
                    "remote_jobs_only": "false",
                    "country": "us",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  ⚠️  JSearch request failed: {e}")
            break

        for item in data.get("data", []):
            salary_min = item.get("job_min_salary")
            salary_max = item.get("job_max_salary")

            # Convert hourly to annual if needed
            period = item.get("job_salary_period", "")
            if period == "HOUR" and salary_min:
                salary_min = int(salary_min * 2080)
                salary_max = int(salary_max * 2080) if salary_max else None

            description = item.get("job_description", "")
            sponsors = detect_sponsorship(description)

            job = Job(
                title=item.get("job_title", ""),
                company=item.get("employer_name", "Unknown"),
                location=f"{item.get('job_city', '')}, {item.get('job_state', '')}".strip(", "),
                source="jsearch",
                url=item.get("job_apply_link") or item.get("job_google_link", ""),
                description=description[:2000],
                salary_min=int(salary_min) if salary_min else None,
                salary_max=int(salary_max) if salary_max else None,
                posted_date=_parse_date(item.get("job_posted_at_datetime_utc")),
                sponsors_h1b=sponsors,
            )
            if job.title and job.company:
                jobs.append(job)

        time.sleep(1)

    return jobs


# ──────────────────────────────────────────────────
# Source 2: Adzuna API (free, 250 req/day)
# ──────────────────────────────────────────────────
# Sign up: https://developer.adzuna.com/

def scrape_adzuna(
    query: str = "data scientist",
    location: str = "New York",
    pages: int = 2,
    app_id: str = "",
    app_key: str = "",
) -> list[Job]:
    """Scrape jobs via Adzuna API."""

    if not app_id:
        app_id = settings.ADZUNA_APP_ID
    if not app_key:
        app_key = settings.ADZUNA_APP_KEY
    if not app_id or not app_key:
        print("  ⚠️  No ADZUNA_APP_ID/ADZUNA_APP_KEY set — skipping Adzuna")
        return []

    jobs = []
    for page in range(1, pages + 1):
        print(f"  📡 Adzuna page {page}/{pages}: '{query}' in {location}...")

        try:
            resp = requests.get(
                f"https://api.adzuna.com/v1/api/jobs/us/search/{page}",
                params={
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": 20,
                    "what": query,
                    "where": location,
                    "salary_min": settings.MIN_SALARY,
                    "sort_by": "date",
                    "max_days_old": 14,
                    "content-type": "application/json",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  ⚠️  Adzuna request failed: {e}")
            break

        for item in data.get("results", []):
            company = item.get("company", {}).get("display_name", "Unknown")
            description = item.get("description", "")
            sponsors = detect_sponsorship(description)

            location_name = item.get("location", {}).get("display_name", "")

            job = Job(
                title=item.get("title", ""),
                company=company,
                location=location_name,
                source="adzuna",
                url=item.get("redirect_url", ""),
                description=description[:2000],
                salary_min=int(item["salary_min"]) if item.get("salary_min") else None,
                salary_max=int(item["salary_max"]) if item.get("salary_max") else None,
                posted_date=_parse_date(item.get("created")),
                sponsors_h1b=sponsors,
            )
            if job.title and job.company:
                jobs.append(job)

        time.sleep(1)

    return jobs


# ──────────────────────────────────────────────────
# Source 3: LinkedIn Public RSS Feeds (no auth)
# ──────────────────────────────────────────────────

def scrape_linkedin_rss(
    query: str = "data scientist",
    location: str = "103644278",  # LinkedIn geoId for US
) -> list[Job]:
    """
    Scrape LinkedIn via public RSS feed. No auth required.
    Limited to ~25 results per query but always works.

    Common LinkedIn geoIds:
        US: 103644278
        New York metro: 90000070
        SF Bay Area: 90000084
        Seattle metro: 91000019
        Boston metro: 90000069
    """
    jobs = []

    # LinkedIn RSS endpoint
    url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {
        "keywords": query,
        "location": location if not location.isdigit() else "",
        "geoId": location if location.isdigit() else "",
        "f_TPR": "r604800",  # Past week
        "start": 0,
    }

    print(f"  📡 LinkedIn RSS: '{query}'...")

    try:
        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": settings.USER_AGENT},
            timeout=15,
        )
        # LinkedIn may return 400/403 — that's fine, we try
        if resp.status_code != 200:
            print(f"  ⚠️  LinkedIn returned {resp.status_code} — trying alternative")
            return _scrape_linkedin_rss_alt(query)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml")

        for card in soup.select("li"):
            title_el = card.select_one("h3.base-search-card__title")
            company_el = card.select_one("h4.base-search-card__subtitle")
            location_el = card.select_one("span.job-search-card__location")
            link_el = card.select_one("a.base-card__full-link")

            if not title_el:
                continue

            job = Job(
                title=title_el.get_text(strip=True),
                company=company_el.get_text(strip=True) if company_el else "Unknown",
                location=location_el.get_text(strip=True) if location_el else "Unknown",
                source="linkedin",
                url=link_el["href"] if link_el and link_el.get("href") else "",
            )
            jobs.append(job)

    except Exception as e:
        print(f"  ⚠️  LinkedIn RSS failed: {e}")

    return jobs


def _scrape_linkedin_rss_alt(query: str) -> list[Job]:
    """Fallback: LinkedIn jobs via Google search."""
    jobs = []
    try:
        # Use LinkedIn's public job search page (no login)
        resp = requests.get(
            "https://www.linkedin.com/jobs/search/",
            params={
                "keywords": query,
                "location": "United States",
                "f_TPR": "r604800",
            },
            headers={"User-Agent": settings.USER_AGENT},
            timeout=15,
        )
        if resp.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            for card in soup.select("div.base-card"):
                title_el = card.select_one("h3")
                company_el = card.select_one("h4")
                loc_el = card.select_one("span.job-search-card__location")
                link_el = card.select_one("a")

                if title_el:
                    jobs.append(Job(
                        title=title_el.get_text(strip=True),
                        company=company_el.get_text(strip=True) if company_el else "Unknown",
                        location=loc_el.get_text(strip=True) if loc_el else "US",
                        source="linkedin",
                        url=link_el["href"] if link_el else "",
                    ))
    except Exception as e:
        print(f"  ⚠️  LinkedIn fallback also failed: {e}")

    return jobs


# ──────────────────────────────────────────────────
# Source 4: RemoteOK API (no auth, remote DS jobs)
# ──────────────────────────────────────────────────

def scrape_remoteok() -> list[Job]:
    """Scrape remote data science jobs from RemoteOK. No auth needed."""
    jobs = []
    print("  📡 RemoteOK: data science remote jobs...")

    try:
        resp = requests.get(
            "https://remoteok.com/api",
            headers={"User-Agent": settings.USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        for item in data[1:]:  # First item is metadata
            tags = [t.lower() for t in item.get("tags", [])]
            title = item.get("position", "").lower()

            # Filter for data science related roles
            ds_keywords = ["data", "scientist", "machine learning", "ml", "analytics", "ai"]
            location_tag = item.get("location", "").lower()
            if location_tag and "us" not in location_tag and "united states" not in location_tag and "remote" not in location_tag and "worldwide" not in location_tag:
                continue

            salary_text = item.get("salary", "")
            salary_min, salary_max = parse_salary(salary_text)
            description = item.get("description", "")
            sponsors = detect_sponsorship(description)

            job = Job(
                title=item.get("position", ""),
                company=item.get("company", "Unknown"),
                location="Remote",
                source="remoteok",
                url=item.get("url", ""),
                description=description[:2000],
                salary_min=salary_min,
                salary_max=salary_max,
                posted_date=_parse_date(item.get("date")),
                sponsors_h1b=sponsors,
            )
            if job.title:
                jobs.append(job)

    except Exception as e:
        print(f"  ⚠️  RemoteOK failed: {e}")

    return jobs


# ──────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Try parsing various date formats."""
    if not date_str:
        return None
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(date_str[:26], fmt)
        except ValueError:
            continue
    return None


# ──────────────────────────────────────────────────
# Main orchestrator
# ──────────────────────────────────────────────────

def run_all_scrapers() -> list[Job]:
    """Run all available scrapers and combine + deduplicate results."""
    all_jobs: list[Job] = []

    # Source 1: JSearch (best coverage, needs free RapidAPI key)
    if settings.RAPIDAPI_KEY:
        for location in settings.LOCATIONS[:4]:  # Limit API calls
            for role in settings.TARGET_ROLES:
                jobs = scrape_jsearch(
                    query=f"{role} visa sponsorship",
                    location=location,
                    pages=1,  # 1 page per location to stay in free tier
                )
                all_jobs.extend(jobs)
                print(f"  ✅ JSearch: {len(jobs)} jobs for '{role}' in {location}")
    else:
        print("  ⏭️  Skipping JSearch (set RAPIDAPI_KEY in .env for best results)")

    # Source 2: Adzuna
    if settings.ADZUNA_APP_ID:
        for location in settings.LOCATIONS[:3]:
            jobs = scrape_adzuna(query="data scientist", location=location, pages=1)
            all_jobs.extend(jobs)
            print(f"  ✅ Adzuna: {len(jobs)} jobs in {location}")
    else:
        print("  ⏭️  Skipping Adzuna (set ADZUNA_APP_ID & ADZUNA_APP_KEY in .env)")

    # Source 3: LinkedIn RSS (always works, no auth)
    print("\n  🔗 LinkedIn public feeds...")
    linkedin_geos = {
        "US": "103644278",
        "New York": "90000070",
        "SF Bay Area": "90000084",
        "Seattle": "91000019",
        "Boston": "90000069",
        "Chicago": "90000084",
        "Austin": "90000049",
    }
    for name, geo_id in linkedin_geos.items():
        jobs = scrape_linkedin_rss(query="data scientist", location=geo_id)
        all_jobs.extend(jobs)
        print(f"  ✅ LinkedIn: {len(jobs)} jobs in {name}")
        time.sleep(settings.REQUEST_DELAY)

    # Source 4: RemoteOK (always works, no auth)
    print("\n  🌐 Remote job boards...")
    remote_jobs = scrape_remoteok()
    all_jobs.extend(remote_jobs)
    print(f"  ✅ RemoteOK: {len(remote_jobs)} remote DS jobs")

    # Deduplicate across all sources
    seen = set()
    unique = []
    for job in all_jobs:
        if job.job_hash not in seen:
            seen.add(job.job_hash)
            unique.append(job)

    print(f"\n📊 Total: {len(all_jobs)} scraped → {len(unique)} unique jobs")
    return unique


if __name__ == "__main__":
    jobs = run_all_scrapers()
    for j in jobs[:10]:
        print(f"  [{j.source}] {j.title} @ {j.company} | {j.salary_display}")
