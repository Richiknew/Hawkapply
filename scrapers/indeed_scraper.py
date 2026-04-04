"""
Indeed job scraper — searches for data science roles with visa sponsorship signals.

Uses requests + BeautifulSoup (no Selenium) for lightweight scraping.
Respects rate limits with configurable delays.

Usage:
    python -m scrapers.indeed_scraper
"""

import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional
from config import settings
from db.models import Job


# Keywords that signal H1B sponsorship in job descriptions
SPONSORSHIP_POSITIVE = [
    "visa sponsorship", "h1b", "h-1b", "sponsor",
    "work authorization", "immigration sponsorship",
    "will sponsor", "sponsorship available",
    "sponsorship provided",
]
SPONSORSHIP_NEGATIVE = [
    "no sponsorship", "not sponsor", "cannot sponsor",
    "will not sponsor", "unable to sponsor",
    "no visa sponsorship", "without sponsorship",
    "must be authorized", "must be eligible",
    "us citizens only", "permanent residents only",
    "no h1b", "no h-1b",
]


def parse_salary(salary_text: str) -> tuple[Optional[int], Optional[int]]:
    """Extract min/max salary from text like '$130,000 - $180,000 a year'."""
    if not salary_text:
        return None, None

    # Find all dollar amounts
    amounts = re.findall(r'\$?([\d,]+(?:\.\d+)?)\s*[kK]?', salary_text)
    parsed = []
    for amt in amounts:
        num = float(amt.replace(",", ""))
        # Handle "130K" style
        if num < 1000 and ("k" in salary_text.lower()):
            num *= 1000
        if num > 10000:  # Filter out non-salary numbers
            parsed.append(int(num))

    if len(parsed) >= 2:
        return min(parsed), max(parsed)
    elif len(parsed) == 1:
        return parsed[0], None
    return None, None


def detect_sponsorship(text: str) -> Optional[bool]:
    """Analyze job text for sponsorship signals. Returns True/False/None."""
    text_lower = text.lower()

    # Check negative signals first (more definitive)
    for phrase in SPONSORSHIP_NEGATIVE:
        if phrase in text_lower:
            return False

    # Check positive signals
    for phrase in SPONSORSHIP_POSITIVE:
        if phrase in text_lower:
            return True

    return None  # Unknown


def scrape_indeed(
    query: str = "data scientist",
    location: str = "New York, NY",
    salary_min: int = 130000,
    max_pages: int = 3,
) -> list[Job]:
    """
    Scrape Indeed for jobs matching the query.

    Args:
        query: Job title search term
        location: City/state to search
        salary_min: Minimum salary filter
        max_pages: Maximum result pages to scrape

    Returns:
        List of Job objects
    """
    jobs: list[Job] = []
    session = requests.Session()
    session.headers.update({
        "User-Agent": settings.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })

    for page in range(max_pages):
        start = page * 10
        url = "https://www.indeed.com/jobs"
        params = {
            "q": f"{query} visa sponsorship",
            "l": location,
            "sort": "date",
            "start": start,
            "fromage": 14,  # Last 14 days
            "salary": str(salary_min),
        }

        print(f"  📄 Page {page + 1}/{max_pages} for '{query}' in {location}...")

        try:
            resp = session.get(url, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  ⚠️  Request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Indeed wraps job cards in various structures — try multiple selectors
        cards = soup.select("div.job_seen_beacon") or soup.select("div.jobsearch-ResultsList > div")

        if not cards:
            print(f"  ℹ️  No results on page {page + 1}")
            break

        for card in cards:
            try:
                job = _parse_indeed_card(card)
                if job:
                    jobs.append(job)
            except Exception as e:
                print(f"  ⚠️  Failed to parse card: {e}")
                continue

        # Rate limiting
        time.sleep(settings.REQUEST_DELAY)

    return jobs


def _parse_indeed_card(card) -> Optional[Job]:
    """Parse a single Indeed job card into a Job object."""

    # Title
    title_el = (
        card.select_one("h2.jobTitle a")
        or card.select_one("a[data-jk]")
        or card.select_one("h2 a")
    )
    if not title_el:
        return None
    title = title_el.get_text(strip=True)

    # Company
    company_el = (
        card.select_one("span[data-testid='company-name']")
        or card.select_one("span.companyName")
        or card.select_one("span.css-1h7lukg")
    )
    company = company_el.get_text(strip=True) if company_el else "Unknown"

    # Location
    location_el = (
        card.select_one("div[data-testid='text-location']")
        or card.select_one("div.companyLocation")
    )
    location = location_el.get_text(strip=True) if location_el else "Unknown"

    # URL
    link = title_el.get("href", "")
    if link and not link.startswith("http"):
        link = f"https://www.indeed.com{link}"
    # Extract clean job key
    jk_match = re.search(r'jk=([a-f0-9]+)', link)
    if jk_match:
        link = f"https://www.indeed.com/viewjob?jk={jk_match.group(1)}"

    # Salary
    salary_el = (
        card.select_one("div.salary-snippet-container")
        or card.select_one("div[class*='salary']")
        or card.select_one("span[class*='salary']")
    )
    salary_text = salary_el.get_text(strip=True) if salary_el else ""
    salary_min, salary_max = parse_salary(salary_text)

    # Snippet/description
    snippet_el = card.select_one("div.job-snippet") or card.select_one("td.resultContent")
    snippet = snippet_el.get_text(strip=True) if snippet_el else ""

    # Detect sponsorship from snippet
    sponsors = detect_sponsorship(snippet)

    return Job(
        title=title,
        company=company,
        location=location,
        source="indeed",
        url=link,
        description=snippet,
        salary_min=salary_min,
        salary_max=salary_max,
        sponsors_h1b=sponsors,
    )


def run_scraper() -> list[Job]:
    """Run the full Indeed scraper across all configured searches."""
    all_jobs: list[Job] = []

    for role in settings.TARGET_ROLES:
        for location in settings.LOCATIONS:
            print(f"\n🔍 Searching: '{role}' in {location}")
            jobs = scrape_indeed(
                query=role,
                location=location,
                salary_min=settings.MIN_SALARY,
                max_pages=settings.MAX_PAGES_PER_SEARCH,
            )
            all_jobs.extend(jobs)
            print(f"  ✅ Found {len(jobs)} jobs")

    # Deduplicate
    seen_hashes = set()
    unique_jobs = []
    for job in all_jobs:
        if job.job_hash not in seen_hashes:
            seen_hashes.add(job.job_hash)
            unique_jobs.append(job)

    print(f"\n📊 Total: {len(all_jobs)} scraped → {len(unique_jobs)} unique jobs")
    return unique_jobs


if __name__ == "__main__":
    jobs = run_scraper()
    for j in jobs[:10]:
        print(f"  {j.title} @ {j.company} | {j.salary_display} | {j.sponsorship_display}")
