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
from datetime import datetime, timedelta
from typing import Callable, Optional
from config import settings
from db.models import Job
from scrapers.indeed_scraper import detect_sponsorship, parse_salary
from scrapers.career_scraper import scrape_all_career_pages


def _is_us_remote(location: str) -> bool:
    """Return True if the location is US-based, Remote, or Worldwide (acceptable for Shreya).
    Returns False for clearly non-US-only locations (India, Europe, APAC, etc.)."""
    if not location:
        return True  # no location = assume remote
    loc = location.lower()
    reject = [
        "india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune", "chennai",
        "china", "shenzhen", "guangzhou", "beijing", "shanghai",
        "canada", "toronto", "vancouver", "montreal",
        "united kingdom", "london", "germany", "berlin", "france", "paris",
        "netherlands", "amsterdam", "australia", "sydney", "melbourne",
        "singapore", "hong kong", "japan", "tokyo", "brazil", "argentina",
        "spain", "madrid", "italy", "milan", "poland", "warsaw", "czech",
        "romania", "europe only", "apac", "latam",
    ]
    if any(r in loc for r in reject):
        return False

    # Check US/remote signals first — these always win
    accept = [
        "united states", "usa", "u.s.", "us only", "us-based", "us remote",
        "remote", "worldwide", "anywhere", "global",
        "new york", "san francisco", "seattle", "boston", "chicago",
        "austin", "los angeles", "denver", "washington", "atlanta",
        ", ny", ", ca", ", wa", ", ma", ", il", ", tx", ", co",
        ", ga", ", pa", ", va", ", md", ", nc", ", nj", ", fl",
    ]
    if any(a in loc for a in accept):
        return True
    return False


def _date_window_days() -> int:
    try:
        days = int(settings.POSTED_WITHIN_DAYS or 7)
    except (TypeError, ValueError):
        return 7
    return min(max(days, 1), 7)


def _jsearch_date_posted_param() -> Optional[str]:
    days = _date_window_days()
    if days <= 1:
        return "today"
    return "week"


def _linkedin_time_range_param() -> Optional[str]:
    days = _date_window_days()
    return f"r{days * 86400}"


def _is_within_posted_window(posted_date: Optional[datetime]) -> bool:
    days = _date_window_days()
    if not posted_date:
        return True  # unknown date → keep, don't silently drop
    cutoff_date = datetime.now().date() - timedelta(days=days - 1)
    return posted_date.date() >= cutoff_date

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
                    "remote_jobs_only": "false",
                    "country": "us",
                    **(
                        {"date_posted": _jsearch_date_posted_param()}
                        if _jsearch_date_posted_param()
                        else {}
                    ),
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  ⚠️  JSearch request failed: {e}")
            if "429" in str(e):
                print("  ⏸️  Rate limited — skipping remaining JSearch queries")
                return jobs  # Return what we have, stop all JSearch
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
                    **(
                        {"max_days_old": _date_window_days()}
                        if _date_window_days() > 0
                        else {}
                    ),
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
        "start": 0,
        **(
            {"f_TPR": _linkedin_time_range_param()}
            if _linkedin_time_range_param()
            else {}
        ),
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
            date_el = card.select_one("time")

            if not title_el:
                continue

            location_text = location_el.get_text(strip=True) if location_el else "Unknown"
            if not _is_us_remote(location_text):
                continue
            posted_date = _parse_date(date_el.get("datetime")) if date_el else None
            if _linkedin_time_range_param() and posted_date is None:
                posted_date = datetime.utcnow()

            job = Job(
                title=title_el.get_text(strip=True),
                company=company_el.get_text(strip=True) if company_el else "Unknown",
                location=location_text,
                source="linkedin",
                url=link_el["href"] if link_el and link_el.get("href") else "",
                posted_date=posted_date,
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
                **(
                    {"f_TPR": _linkedin_time_range_param()}
                    if _linkedin_time_range_param()
                    else {}
                ),
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
                date_el = card.select_one("time")

                if title_el:
                    location_text = loc_el.get_text(strip=True) if loc_el else "US"
                    if not _is_us_remote(location_text):
                        continue
                    posted_date = _parse_date(date_el.get("datetime")) if date_el else None
                    if _linkedin_time_range_param() and posted_date is None:
                        posted_date = datetime.utcnow()
                    jobs.append(Job(
                        title=title_el.get_text(strip=True),
                        company=company_el.get_text(strip=True) if company_el else "Unknown",
                        location=location_text,
                        source="linkedin",
                        url=link_el["href"] if link_el else "",
                        posted_date=posted_date,
                    ))
    except Exception as e:
        print(f"  ⚠️  LinkedIn fallback also failed: {e}")

    return jobs

def enrich_missing_descriptions(jobs: list[Job]) -> list[Job]:
    """Fetch full JD for jobs with empty descriptions."""
    from bs4 import BeautifulSoup
    
    # empty = [j for j in jobs if not j.description.strip()]
    empty = [j for j in jobs if not (j.description or "").strip()]
    print(f"\n  📥 Enriching {len(empty)} jobs with missing descriptions...")
    
    for i, job in enumerate(empty):
        if not job.url:
            continue
        try:
            resp = requests.get(job.url, timeout=10,
                               headers={"User-Agent": settings.USER_AGENT})
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            
            # LinkedIn public job pages
            desc_el = (
                soup.select_one("div.description__text") or
                soup.select_one("div.show-more-less-html__markup") or
                soup.select_one("div[class*='description']") or
                soup.select_one("section[class*='description']")
            )
            if desc_el:
                job.description = desc_el.get_text(separator=" ", strip=True)[:2000]
                
        except Exception:
            continue
        
        time.sleep(1)  # Be polite
        
        if (i + 1) % 10 == 0:
            print(f"    Enriched {i+1}/{len(empty)}...")
    
    filled = len([j for j in empty if j.description.strip()])
    print(f"  ✅ Filled {filled}/{len(empty)} missing descriptions")
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
            ds_keywords = ["data scientist", "data science", "machine learning", "deep learning", "ml engineer", "ai engineer", "applied scientist", "nlp", "computer vision"]
            ds_tags = ["data", "ml", "machine-learning", "data-science", "ai"]
            if not (any(kw in title for kw in ds_keywords) or any(t in tags for t in ds_tags)):
                continue
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
# Source 6: Arbeitnow (visa sponsorship filter built in!)
# ──────────────────────────────────────────────────

def scrape_arbeitnow() -> list[Job]:
    """Free API, no auth. Has a visa_sponsorship filter!"""
    jobs = []
    print("  📡 Arbeitnow: visa sponsorship jobs...")
    
    for page in range(1, 4):
        try:
            resp = requests.get(
                "https://www.arbeitnow.com/api/job-board-api",
                params={"visa_sponsorship": "true", "page": page},
                timeout=15, headers={"User-Agent": settings.USER_AGENT},
            )
            if resp.status_code != 200:
                break
            data = resp.json()
        except Exception as e:
            print(f"  ⚠️  Arbeitnow failed: {e}")
            break

        for item in data.get("data", []):
            title = item.get("title", "")
            location = item.get("location", "")
            # Arbeitnow is a German board — only keep US/Remote entries
            if not _is_us_remote(location):
                continue
            ds_keywords = ["data scientist", "data science", "machine learning", "ml engineer",
                           "ai engineer", "applied scientist", "nlp", "data analyst", "data engineer"]
            if not any(kw in title.lower() for kw in ds_keywords):
                continue
            job = Job(
                title=title,
                company=item.get("company_name", "Unknown"),
                location=location,
                source="arbeitnow",
                url=item.get("url", ""),
                description=item.get("description", "")[:2000],
                posted_date=datetime.fromtimestamp(item["created_at"]) if item.get("created_at") else None,
                sponsors_h1b=True,
            )
            if job.title:
                jobs.append(job)

        if not data.get("links", {}).get("next"):
            break
        time.sleep(1)

    return jobs


# ──────────────────────────────────────────────────
# Source 7: Remotive (remote DS/ML jobs)
# ──────────────────────────────────────────────────

def scrape_remotive() -> list[Job]:
    """Free API, no auth. Good remote ML/DS coverage."""
    jobs = []
    print("  📡 Remotive: remote data/ML jobs...")

    for category in ["data", "machine-learning"]:
        try:
            resp = requests.get(
                "https://remotive.com/api/remote-jobs",
                params={"category": category, "limit": 50},
                timeout=15, headers={"User-Agent": settings.USER_AGENT},
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception as e:
            print(f"  ⚠️  Remotive failed: {e}")
            continue

        for item in data.get("jobs", []):
            loc = item.get("candidate_required_location", "Remote")
            # Only keep US, worldwide, or truly remote (no country specified)
            if not _is_us_remote(loc):
                continue
            job = Job(
                title=item.get("title", ""),
                company=item.get("company_name", "Unknown"),
                location=loc,
                source="remotive",
                url=item.get("url", ""),
                description=item.get("description", "")[:2000],
                salary_min=item.get("salary_min"),
                salary_max=item.get("salary_max"),
                posted_date=_parse_date(item.get("publication_date")),
            )
            if job.title:
                jobs.append(job)

        time.sleep(1)

    return jobs


# ──────────────────────────────────────────────────
# Source 8: Jobicy (remote jobs, US/Americas focus)
# ──────────────────────────────────────────────────

def scrape_jobicy() -> list[Job]:
    """Free API, no auth. Supports geo and tag filters."""
    jobs = []
    print("  📡 Jobicy: remote DS jobs (USA)...")

    for tag in ["data-scientist", "machine-learning", "python"]:
        try:
            resp = requests.get(
                "https://jobicy.com/api/v2/remote-jobs",
                params={"count": 50, "geo": "usa", "tag": tag},
                timeout=15, headers={"User-Agent": settings.USER_AGENT},
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception as e:
            print(f"  ⚠️  Jobicy failed: {e}")
            continue

        for item in data.get("jobs", []):
            sal_min, sal_max = None, None
            if item.get("annualSalaryMin"):
                sal_min = int(item["annualSalaryMin"])
            if item.get("annualSalaryMax"):
                sal_max = int(item["annualSalaryMax"])

            job = Job(
                title=item.get("jobTitle", ""),
                company=item.get("companyName", "Unknown"),
                location=item.get("jobGeo", "Remote"),
                source="jobicy",
                url=item.get("url", ""),
                description=item.get("jobDescription", "")[:2000],
                salary_min=sal_min,
                salary_max=sal_max,
                posted_date=_parse_date(item.get("pubDate")),
            )
            if job.title:
                jobs.append(job)

        time.sleep(1)

    return jobs


# ──────────────────────────────────────────────────
# Source 9: Himalayas (visa sponsorship filter built-in!)
# ──────────────────────────────────────────────────

def scrape_himalayas() -> list[Job]:
    """Free API, no auth. Filters for visa sponsorship jobs."""
    jobs = []
    print("  📡 Himalayas: visa-sponsored DS jobs...")
    ds_queries = ["data scientist", "machine learning", "data science", "ml engineer"]

    for query in ds_queries:
        try:
            resp = requests.get(
                "https://himalayas.app/jobs/api",
                params={"q": query, "limit": 100},
                timeout=15,
                headers={"User-Agent": settings.USER_AGENT},
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for item in data.get("jobs", []):
                location = item.get("location", "") or ""
                if not _is_us_remote(location):
                    continue
                title = item.get("title", "")
                description = item.get("description", "") or ""
                sponsors = item.get("visaSponsorship", False) or detect_sponsorship(description)
                salary_text = item.get("salary", "") or ""
                salary_min, salary_max = parse_salary(salary_text)
                job = Job(
                    title=title,
                    company=item.get("companyName", "Unknown"),
                    location=location or "Remote",
                    source="himalayas",
                    url=item.get("url", "") or item.get("applyUrl", ""),
                    description=description[:2000],
                    salary_min=salary_min,
                    salary_max=salary_max,
                    posted_date=_parse_date(item.get("createdAt")),
                    sponsors_h1b=sponsors,
                )
                if job.title:
                    jobs.append(job)
        except Exception as e:
            print(f"  ⚠️  Himalayas failed for '{query}': {e}")
        time.sleep(1)

    return jobs


# ──────────────────────────────────────────────────
# Source 10: The Muse (free public API, no auth)
# ──────────────────────────────────────────────────

def scrape_the_muse() -> list[Job]:
    """Free public API, 500 req/day, no auth needed."""
    jobs = []
    print("  📡 The Muse: data science jobs...")
    ds_categories = ["Data Science", "Data + Analytics"]

    for category in ds_categories:
        for page in range(1, 4):
            try:
                resp = requests.get(
                    "https://www.themuse.com/api/public/jobs",
                    params={
                        "category": category,
                        "page": page,
                        "descended": "true",
                    },
                    timeout=15,
                    headers={"User-Agent": settings.USER_AGENT},
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                results = data.get("results", [])
                if not results:
                    break

                for item in results:
                    # Location filter
                    locations = item.get("locations", [])
                    location_names = [loc.get("name", "") for loc in locations]
                    location_str = ", ".join(location_names) if location_names else "Remote"
                    if location_names and not any(_is_us_remote(l) for l in location_names):
                        continue

                    title = item.get("name", "")
                    company = item.get("company", {}).get("name", "Unknown")
                    url = item.get("refs", {}).get("landing_page", "")
                    contents = item.get("contents", "")
                    description = re.sub(r"<[^>]+>", " ", contents)[:2000]
                    sponsors = detect_sponsorship(description)
                    published = item.get("publication_date", "")

                    job = Job(
                        title=title,
                        company=company,
                        location=location_str,
                        source="themuse",
                        url=url,
                        description=description,
                        posted_date=_parse_date(published),
                        sponsors_h1b=sponsors,
                    )
                    if job.title:
                        jobs.append(job)

            except Exception as e:
                print(f"  ⚠️  The Muse failed page {page} for '{category}': {e}")
                break
            time.sleep(1)

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

ProgressCallback = Callable[[str, int], None]


def _emit_progress(progress_cb: Optional[ProgressCallback], message: str, total_jobs: int) -> None:
    if progress_cb:
        progress_cb(message, total_jobs)


def run_all_scrapers(progress_cb: Optional[ProgressCallback] = None) -> list[Job]:
    """Run all available scrapers and combine + deduplicate results."""
    all_jobs: list[Job] = []

    _emit_progress(progress_cb, "Starting job scrape", 0)

    # Source 1: JSearch (best coverage, needs free RapidAPI key)
    if settings.RAPIDAPI_KEY:
        # Core roles + domain-specific queries
        search_queries = list(settings.TARGET_ROLES) + [
            "data scientist marketing",
            "data scientist advertising",
            "data scientist finance",
            "data scientist logistics",
            "data scientist supply chain",
            "data scientist media",
            "data scientist risk",
            "ML engineer fintech",
        ]
        # Deduplicate and limit to stay in free tier
        search_queries = list(dict.fromkeys(search_queries))[:8]

        for location in settings.LOCATIONS[:3]: # limit locations to stay in free tier for first 3 locations
            for query in search_queries:
                jobs = scrape_jsearch(
                    query=query,
                    location=location,
                    pages=1, # 1 page per location/query to stay within free limits
                )
                all_jobs.extend(jobs)
                print(f"  ✅ JSearch: {len(jobs)} jobs for '{query}' in {location}")
                _emit_progress(
                    progress_cb,
                    f"Scraping JSearch: {query} in {location}",
                    len(all_jobs),
                )
    else:
        print("  ⏭️  Skipping JSearch (set RAPIDAPI_KEY in .env for best results)")
        _emit_progress(progress_cb, "Skipping JSearch (no RapidAPI key)", len(all_jobs))

    # Source 2: Adzuna
    if settings.ADZUNA_APP_ID:
        for location in settings.LOCATIONS[:3]:
            jobs = scrape_adzuna(query="data scientist", location=location, pages=1)
            all_jobs.extend(jobs)
            print(f"  ✅ Adzuna: {len(jobs)} jobs in {location}")
            _emit_progress(
                progress_cb,
                f"Scraping Adzuna: data scientist in {location}",
                len(all_jobs),
            )
    else:
        print("  ⏭️  Skipping Adzuna (set ADZUNA_APP_ID & ADZUNA_APP_KEY in .env)")
        _emit_progress(progress_cb, "Skipping Adzuna (no API credentials)", len(all_jobs))

    # Source 3: LinkedIn RSS (always works, no auth)
    print("\n  🔗 LinkedIn public feeds...")
    linkedin_geos = {
        "US": "103644278",
        "New York": "90000070",
        "SF Bay Area": "90000084",
        "Seattle": "91000019",
        "Boston": "90000069",
        "Washington DC": "90000097",
        "Philadelphia": "90000022",
        "Atlanta": "90000051",
        "Chicago": "90000084",
        "Dallas": "90000049",
        "Los Angeles": "90000058",
        "Denver": "90000048",
    }
    for name, geo_id in linkedin_geos.items():
        for role in settings.TARGET_ROLES:
            jobs = scrape_linkedin_rss(query=role, location=geo_id)
            all_jobs.extend(jobs)
            print(f"  ✅ LinkedIn: {len(jobs)} jobs for '{role}' in {name}")
            _emit_progress(
                progress_cb,
                f"Scraping LinkedIn: {role} in {name}",
                len(all_jobs),
            )
            time.sleep(settings.REQUEST_DELAY)

    # Source 4: RemoteOK (always works, no auth)
    print("\n  🌐 Remote job boards...")
    remote_jobs = scrape_remoteok()
    all_jobs.extend(remote_jobs)
    print(f"  ✅ RemoteOK: {len(remote_jobs)} remote DS jobs")
    _emit_progress(progress_cb, "Scraping RemoteOK", len(all_jobs))
    ds_title_words = [
        "data scien", "machine learn", "ml ", "deep learn",
        "nlp", "ai research", "ai engineer", "data engineer",
        "analytics engineer", "mlops", "applied scien",
        "research scien", "computer vision", "ml ops",
        "marketing scien", "marketing analy", "ad tech",
        "risk analy", "quant",
        "supply chain analy", "logistics analy", "forecast",
        "media mix", "attribution", "pricing analy",
    ]
    

    # Source 5: Direct career pages of H1B sponsors (no API key needed)
    print("\n  🏢 H1B sponsor career pages...")
    career_jobs = scrape_all_career_pages()
    all_jobs.extend(career_jobs)
    _emit_progress(progress_cb, "Scraping H1B sponsor career pages", len(all_jobs))
    
    # Source 6: Arbeitnow (has visa sponsorship filter!)
    arbeitnow_jobs = scrape_arbeitnow()
    all_jobs.extend(arbeitnow_jobs)
    print(f"  ✅ Arbeitnow: {len(arbeitnow_jobs)} visa sponsorship jobs")
    _emit_progress(progress_cb, "Scraping Arbeitnow", len(all_jobs))

    # Source 7: Remotive
    remotive_jobs = scrape_remotive()
    all_jobs.extend(remotive_jobs)
    print(f"  ✅ Remotive: {len(remotive_jobs)} remote DS/ML jobs")
    _emit_progress(progress_cb, "Scraping Remotive", len(all_jobs))

    # Source 8: Jobicy
    jobicy_jobs = scrape_jobicy()
    all_jobs.extend(jobicy_jobs)
    print(f"  ✅ Jobicy: {len(jobicy_jobs)} remote DS jobs (USA)")
    _emit_progress(progress_cb, "Scraping Jobicy", len(all_jobs))

    # Source 9: Himalayas (visa sponsorship filter built-in)
    himalayas_jobs = scrape_himalayas()
    all_jobs.extend(himalayas_jobs)
    print(f"  ✅ Himalayas: {len(himalayas_jobs)} visa-sponsored DS jobs")
    _emit_progress(progress_cb, "Scraping Himalayas", len(all_jobs))

    # Source 10: The Muse (free public API)
    muse_jobs = scrape_the_muse()
    all_jobs.extend(muse_jobs)
    print(f"  ✅ The Muse: {len(muse_jobs)} DS/analytics jobs")
    _emit_progress(progress_cb, "Scraping The Muse", len(all_jobs))

    if _date_window_days() > 0:
        all_jobs = [j for j in all_jobs if _is_within_posted_window(j.posted_date)]
        _emit_progress(
            progress_cb,
            f"Filtering jobs posted within the last {_date_window_days()} day(s)",
            len(all_jobs),
        )


    all_jobs = enrich_missing_descriptions(all_jobs)
    _emit_progress(progress_cb, "Enriching missing descriptions", len(all_jobs))
    # Title filter + level filter (applies to ALL sources)
    # exclude_levels = ["staff", "director", "principal", "vp ", "vice president", "head of", "chief", "lead", "manager", "senior staff", "distinguished", "intern", "phd", "ph.d", "doctorate", "postdoc", "fellow"]
    # exclude_clearance = ["ts/sci", "top secret", "secret clearance", "security clearance", "clearance required", "us citizen", "citizenship required", "public trust"]
    # all_jobs = [
    #     j for j in all_jobs
    #     if any(kw in j.title.lower() for kw in ds_title_words)
    #     and not any(lvl in j.title.lower() for lvl in exclude_levels)
    #     and not any(cl in (j.title + " " + j.description).lower() for cl in exclude_clearance)
    # ]
    exclude_title = [
        "staff", "director", "principal", "vp ", "vice president",
        "head of", "chief", "lead", "manager", "senior staff",
        "distinguished", "intern", "phd", "ph.d", "doctorate",
        "postdoc", "fellow", "co-op", "apprentice",
    ]
    exclude_description = [
        # Clearance
        "ts/sci", "top secret", "secret clearance", "security clearance",
        "clearance required", "public trust", "polygraph", "poly required",
        "sci clearance", "active clearance", "dod clearance",
        # No sponsorship — explicit rejections
        "no sponsorship", "not sponsor", "cannot sponsor",
        "will not sponsor", "unable to sponsor", "without sponsorship",
        "does not sponsor", "do not sponsor", "not able to sponsor",
        "not in a position to sponsor", "sponsorship is not available",
        "sponsorship not available", "sponsorship not provided",
        "visa sponsorship is not", "visa sponsorship will not",
        "employment-based sponsorship not",
        # OPT / CPT specific rejections
        "no opt", "no cpt", "no opt/cpt", "no opt, cpt",
        "opt not", "cpt not", "opt/cpt not",
        "opt candidates not", "cpt candidates not",
        "not accepting opt", "not accepting cpt",
        "opt is not", "cpt is not",
        # H1B / visa specific rejections
        "no h1b", "no h-1b", "no h1-b", "no visa",
        "h1b not", "h-1b not", "h1b transfer not",
        "no visa transfer", "visa transfers not",
        # Citizenship / PR only
        "us citizen", "u.s. citizen", "citizenship required",
        "must be a citizen", "citizens only",
        "permanent resident only", "green card required",
        "must be a us", "must be a u.s.",
        # PhD/Intern
        "phd required", "ph.d. required", "doctoral degree required",
        "internship program", "intern position", "summer intern",
        "new grad program", "co-op program",
        # Government/defense only
        "government contractor only", "federal employee",
        "military experience required",
    ]
    def _too_senior(text: str) -> bool:
        """Check if JD explicitly requires 7+ years of experience."""
        patterns = [
            r'(\d+)\+\s*years?\s+of\s+(?:experience|exp)',
            r'(\d+)\+\s*yrs?\s+(?:of\s+)?(?:experience|exp)',
            r'minimum\s+(?:of\s+)?(\d+)\s+years?\s+(?:of\s+)?(?:experience|exp)',
            r'at\s+least\s+(\d+)\s+years?\s+(?:of\s+)?(?:experience|exp)',
            r'(\d+)\s*[-–]\s*\d+\s+years?\s+of\s+experience',
            r'requires?\s+(\d+)\+?\s+years?\s+(?:of\s+)?(?:experience|exp)',
        ]
        for pat in patterns:
            for m in re.findall(pat, text.lower()):
                if int(m) >= 7:
                    return True
        return False
    all_jobs = [
        j for j in all_jobs
        if any(kw in j.title.lower() for kw in ds_title_words)
        and not any(lvl in j.title.lower() for lvl in exclude_title)
        and not any(ex in (j.title + " " + j.description).lower() for ex in exclude_description)
        and not _too_senior(j.title + " " + j.description)
    ]
    print(f"📋 After title filtering: {len(all_jobs)} relevant jobs")
    _emit_progress(progress_cb, "Filtering for relevant roles", len(all_jobs))

    # Deduplicate across all sources by job_hash
    seen = set()
    unique = []
    for job in all_jobs:
        if job.job_hash not in seen:
            seen.add(job.job_hash)
            unique.append(job)

    # Secondary dedup: same company + near-identical title = repost
    # Sort newest-first so we keep the most recent posting when deduping
    def _norm_title(t: str) -> str:
        t = t.lower()
        for strip in ["i", "ii", "iii", "iv", "1", "2", "3", "sr.", "sr", "senior", "junior", "jr", "jr."]:
            t = re.sub(rf'\b{re.escape(strip)}\b', '', t)
        return re.sub(r'[^a-z0-9 ]', '', t).strip()

    from datetime import timezone
    unique.sort(key=lambda j: j.posted_date or datetime.min, reverse=True)

    seen_company_title = set()
    deduped = []
    for job in unique:
        key = (job.company.lower().strip(), _norm_title(job.title))
        if key not in seen_company_title:
            seen_company_title.add(key)
            deduped.append(job)
        # If same company+title seen before but this one is from a different day
        # (genuinely new posting), keep it too
        else:
            existing = next(j for j in deduped if
                (j.company.lower().strip(), _norm_title(j.title)) == key)
            if (existing.posted_date and job.posted_date and
                    abs((existing.posted_date - job.posted_date).days) >= 7):
                deduped.append(job)

    removed = len(unique) - len(deduped)
    if removed:
        print(f"🔁 Removed {removed} reposted jobs (same company+title)")
    unique = deduped

    print(f"\n📊 Total: {len(all_jobs)} scraped → {len(unique)} unique jobs")
    _emit_progress(progress_cb, "Deduplicated scraped jobs", len(unique))
    return unique


if __name__ == "__main__":
    jobs = run_all_scrapers()
    for j in jobs[:10]:
        print(f"  [{j.source}] {j.title} @ {j.company} | {j.salary_display}")
