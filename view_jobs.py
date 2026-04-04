"""
HawkApply — Job Viewer CLI

Browse, filter, and manage scraped jobs from the terminal.

Usage:
    python view_jobs.py                    # Show top jobs
    python view_jobs.py --all              # Show all jobs
    python view_jobs.py --sponsors         # Only H1B sponsors
    python view_jobs.py --min-score 60     # Filter by score
    python view_jobs.py --min-salary 150000
    python view_jobs.py --stats            # Show summary stats
    python view_jobs.py --export csv       # Export to CSV
"""

import sys
import csv
import argparse
from io import StringIO
from db import operations as ops
from utils.scorer import score_tier


def print_jobs(jobs: list[dict], verbose: bool = False):
    """Pretty-print a list of jobs."""
    if not jobs:
        print("  No jobs found matching your filters.")
        return

    for i, j in enumerate(jobs, 1):
        tier = score_tier(j["h1b_score"] or 0)

        # Salary display
        if j["salary_min"] and j["salary_max"]:
            salary = f"${j['salary_min']:,} - ${j['salary_max']:,}"
        elif j["salary_min"]:
            salary = f"${j['salary_min']:,}+"
        elif j["h1b_avg_salary"]:
            salary = f"~${j['h1b_avg_salary']:,} (H1B avg)"
        else:
            salary = "Not listed"

        # Sponsorship
        if j["sponsors_h1b"] is True:
            sponsor = f"✅ Sponsors ({j['h1b_filings']} filings)"
        elif j["sponsors_h1b"] is False:
            sponsor = "❌ No sponsorship"
        else:
            sponsor = "❓ Unknown"

        print(f"\n{'─' * 60}")
        print(f"  #{i}  {tier}  Score: {j['h1b_score'] or 0}")
        print(f"  📋 {j['title']}")
        print(f"  🏢 {j['company']}  |  📍 {j['location']}")
        print(f"  💰 {salary}  |  🏛️ {sponsor}")
        print(f"  🔗 {j['url'][:80]}")
        print(f"  📅 Status: {j['status']}  |  Source: {j['source']}")

        if verbose and j["description"]:
            print(f"  📝 {j['description'][:200]}...")

    print(f"\n{'─' * 60}")
    print(f"  Showing {len(jobs)} jobs")


def print_stats():
    """Print database summary statistics."""
    stats = ops.get_job_stats()
    if not stats:
        print("  No data in database yet. Run 'python main.py' first.")
        return

    print("\n📊 HawkApply Database Stats")
    print("─" * 40)
    print(f"  Total jobs:            {stats['total_jobs']}")
    print(f"  H1B sponsors:          {stats['sponsoring_jobs']}")
    print(f"  Salary ≥ $130K:        {stats['high_salary_jobs']}")
    print(f"  New (unapplied):       {stats['new_jobs']}")
    print(f"  Applied:               {stats['applied_jobs']}")
    print(f"  Unique companies:      {stats['unique_companies']}")
    print(f"  Average H1B score:     {stats['avg_score']}")


def export_csv(jobs: list[dict]) -> str:
    """Export jobs to CSV string."""
    if not jobs:
        return ""

    output = StringIO()
    fields = [
        "title", "company", "location", "salary_min", "salary_max",
        "h1b_score", "h1b_filings", "h1b_avg_salary", "sponsors_h1b",
        "status", "url", "source",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for j in jobs:
        writer.writerow(j)

    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description="HawkApply Job Viewer")
    parser.add_argument("--all", action="store_true", help="Show all jobs")
    parser.add_argument("--sponsors", action="store_true", help="Only H1B sponsors")
    parser.add_argument("--min-score", type=float, default=0, help="Minimum H1B score")
    parser.add_argument("--min-salary", type=int, default=0, help="Minimum salary")
    parser.add_argument("--status", type=str, default=None, help="Filter by status")
    parser.add_argument("--limit", type=int, default=20, help="Max results")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show descriptions")
    parser.add_argument("--stats", action="store_true", help="Show summary stats")
    parser.add_argument("--export", type=str, choices=["csv"], help="Export format")

    args = parser.parse_args()

    if args.stats:
        print_stats()
        return

    limit = 1000 if args.all else args.limit

    jobs = ops.get_jobs(
        status=args.status,
        min_score=args.min_score,
        min_salary=args.min_salary or None,
        sponsors_only=args.sponsors,
        limit=limit,
    )

    if args.export == "csv":
        csv_data = export_csv(jobs)
        filename = "hawkapply_jobs.csv"
        with open(filename, "w") as f:
            f.write(csv_data)
        print(f"✅ Exported {len(jobs)} jobs to {filename}")
    else:
        print_jobs(jobs, verbose=args.verbose)


if __name__ == "__main__":
    main()
