"""
HawkApply — Main Pipeline Orchestrator

Runs the full Phase 1 pipeline:
  1. Scrape jobs from Indeed
  2. Store in Neon PostgreSQL
  3. Load/refresh H1B sponsor data
  4. Cross-reference and score every job
  5. Print summary

Usage:
    python main.py
    python main.py --refresh-h1b    # Force refresh H1B data
"""

import sys
import time
from datetime import datetime

from config import settings
from db.init_db import init_database
from db import operations as ops
from db.models import Job
# from scrapers.indeed_scraper import run_scraper
from scrapers.job_scraper import run_all_scrapers
from scrapers.h1b_matcher import match_jobs_with_sponsors, load_or_refresh_sponsors
from utils.scorer import score_tier


def run_pipeline(refresh_h1b: bool = False):
    """Execute the full scraping + matching pipeline."""

    start_time = time.time()
    print("=" * 60)
    print("🦅 HawkApply — Job Scraping Pipeline")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 0: Ensure database is initialized
    print("\n📦 Step 0: Initializing database...")
    try:
        init_database()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("   → Make sure your DATABASE_URL is set in .env")
        print("   → Get your connection string from https://neon.tech")
        sys.exit(1)

    # Step 1: Scrape jobs
    print("\n🔍 Step 1: Scraping jobs from Indeed...")
    print(f"   Roles:     {', '.join(settings.TARGET_ROLES)}")
    print(f"   Locations: {', '.join(settings.LOCATIONS)}")
    print(f"   Min salary: ${settings.MIN_SALARY:,}")

    jobs = run_scraper()

    # Step 2: Store in database
    print(f"\n💾 Step 2: Storing {len(jobs)} jobs in Neon PostgreSQL...")
    new_count = ops.upsert_jobs_batch(jobs)
    print(f"   → {new_count} new jobs added, {len(jobs) - new_count} duplicates skipped")

    # Step 3: H1B matching
    print("\n🏛️ Step 3: Cross-referencing with H1B sponsorship data...")
    if refresh_h1b:
        load_or_refresh_sponsors(force_refresh=True)
    match_jobs_with_sponsors()

    # Step 4: Summary
    print("\n" + "=" * 60)
    print("📊 Pipeline Summary")
    print("=" * 60)

    stats = ops.get_job_stats()
    if stats:
        print(f"   Total jobs in database:    {stats['total_jobs']}")
        print(f"   H1B-sponsoring companies:  {stats['sponsoring_jobs']}")
        print(f"   Salary ≥ $130K:            {stats['high_salary_jobs']}")
        print(f"   New (unapplied):           {stats['new_jobs']}")
        print(f"   Already applied:           {stats['applied_jobs']}")
        print(f"   Unique companies:          {stats['unique_companies']}")
        print(f"   Average H1B score:         {stats['avg_score']}")

    # Show top 5 jobs
    top_jobs = ops.get_jobs(sponsors_only=True, min_salary=settings.MIN_SALARY, limit=5)
    if top_jobs:
        print(f"\n🏆 Top {len(top_jobs)} Jobs (H1B score + salary):")
        print("-" * 60)
        for j in top_jobs:
            tier = score_tier(j["h1b_score"])
            salary = f"${j['salary_min']:,}" if j["salary_min"] else f"~${j['h1b_avg_salary']:,}" if j["h1b_avg_salary"] else "N/A"
            print(f"   {tier} [{j['h1b_score']}] {j['title']}")
            print(f"      📍 {j['company']} — {j['location']} | 💰 {salary}")
            print(f"      🔗 {j['url'][:80]}...")
            print()

    elapsed = time.time() - start_time
    print(f"⏱️  Pipeline completed in {elapsed:.1f}s")
    print(f"💡 Run 'python view_jobs.py' to browse all results")


if __name__ == "__main__":
    refresh = "--refresh-h1b" in sys.argv
    run_pipeline(refresh_h1b=refresh)
