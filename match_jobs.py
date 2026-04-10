"""
Match Pipeline — parse JDs and match against resume for all scraped jobs.

Usage:
    python match_jobs.py                    # Match all new jobs (fast mode)
    python match_jobs.py --ai               # Use AI for top matches
    python match_jobs.py --top 20           # Show top 20
    python match_jobs.py --min-score 60     # Only show 60+ matches
    python match_jobs.py --export           # Export results to CSV
"""

import argparse
import csv
import json
import time
from db import operations as ops
from parsers.jd_parser import parse_jd
from parsers.resume_matcher import match_resume_fast, match_resume_ai
from tqdm import tqdm
from db.operations import upsert_match_result
from db.operations import get_connection

import re

def parse_jd_local(description: str) -> dict:
    """Quick keyword extraction from JD text. No API call."""
    desc = description.lower()
    
    langs = []
    for lang in ["python", "sql", "pyspark", "r ", "python","pytorch", "sas"]:
        if lang in desc:
            langs.append(lang.strip())
    
    tools = []
    for tool in ["databricks", "aws", "gcp", "azure", "spark", "hadoop", "airflow",
                  "dbt", "tableau", "power bi", "snowflake", "redshift", "bigquery",
                  "sagemaker", "mlflow", "docker", "kubernetes", "git", "jenkins",
                   "kafka", "s3", "ec2", "emr", "glue", "looker"]:
        if tool in desc:
            tools.append(tool)
    
    ml = []
    for technique in ["logistic regression", "random forest", "xgboost", "deep learning",
                       "neural network", "nlp", "computer vision", "a/b test", "hypothesis test",
                       "clustering", "classification", "regression", "time series",
                       "recommendation", "reinforcement learning", "transformer",
                       "lstm", "cnn", "bert", "llm", "generative ai", "causal inference",
                       "bayesian", "gradient boost", "feature engineering"]:
        if technique in desc:
            ml.append(technique)
    
    domains = []
    for domain in ["marketing", "advertising", "finance", "banking", "insurance",
                    "healthcare", "retail", "e-commerce", "supply chain", "logistics",
                    "media", "ad tech", "risk", "fraud", "pricing", "forecasting"]:
        if domain in desc:
            domains.append(domain)
    
    yrs_match = re.search(r'(\d+)\+?\s*(?:years|yrs)', desc)
    yrs = int(yrs_match.group(1)) if yrs_match else -1
    
    return {
        "programming_languages": langs,
        "tools_and_platforms": tools,
        "ml_techniques": ml,
        "domain_knowledge": domains,
        "years_experience_min": yrs,
        "education": {"degree": "masters" if "master" in desc else "bachelors" if "bachelor" in desc else "", "fields": []},
        "required_skills": langs + tools + ml,
        "preferred_skills": [],
    }
def run_matching(use_ai: bool = False, top_n: int = 20,
                 min_score: float = 0, ai_threshold: float = 60.0):
    """Parse JDs and match all jobs against Shreya's resume."""

    print("=" * 60)
    print("🎯 HawkApply — JD Parser + Resume Matcher")
    print("=" * 60)

    # Get all jobs with descriptions
    jobs = ops.get_jobs(status="new", sponsors_only=False, limit=500)
    # jobs_with_desc = [j for j in jobs if j.get("description", "").strip()]
    jobs_with_desc = [j for j in jobs if j.get("description", "").strip()]
    jobs_with_desc.sort(key=lambda x: x.get("h1b_score", 0), reverse=True)
    jobs_with_desc = jobs_with_desc[:50]  # Limit to top 50 by H1B score for parsing/matching to stay within API budget

    print(f"\n📋 {len(jobs)} total jobs, {len(jobs_with_desc)} have descriptions to parse")

    if not jobs_with_desc:
        print("❌ No jobs with descriptions found. Run main.py first.")
        return []
    
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE match_results;")
        conn.commit()
    conn.close()
    print("  🗑️  Cleared old match results")

    results = []
    start = time.time()

    api_failed = False
    for i, job in tqdm(enumerate(jobs_with_desc), total=len(jobs_with_desc), desc="  🔍 Parsing & matching"):
        if api_failed:
            # Skip API, use empty parse
            fast_result = match_resume_fast({})
            results.append({
                "rank": 0, "title": job["title"], "company": job["company"],
                "location": job["location"], "url": job["url"],
                "h1b_score": job.get("h1b_score", 0), "match_score": fast_result["total_score"],
                "fit_tier": fast_result["fit_tier"], "strengths": [], "gaps": [],
                "cover_letter_angles": [], "source": job["source"], "job_hash": job["job_hash"],
            })
            continue
        title = job["title"]
        company = job["company"]

        # Step 1: Parse JD
        if use_ai and not api_failed:
            try:
                parsed_jd = parse_jd(
                    description=job["description"],
                    title=title,
                    company=company,
                )
            except Exception as e:
                print(f"  ❌ API quota exhausted. Switching to local parsing.")
                api_failed = True
                parsed_jd = parse_jd_local(job["description"])
        else:
            parsed_jd = parse_jd_local(job["description"])

        if not parsed_jd.get("required_skills") and not parsed_jd.get("programming_languages"):
            # JD too short or parsing failed — use fast match only
            fast_result = match_resume_fast(parsed_jd)
            results.append({
                "rank": 0,
                "title": title,
                "company": company,
                "location": job["location"],
                "url": job["url"],
                "h1b_score": job.get("h1b_score", 0),
                "match_score": fast_result["total_score"],
                "fit_tier": fast_result["fit_tier"],
                "strengths": fast_result.get("strengths", []),
                "gaps": fast_result.get("gaps", []),
                "cover_letter_angles": [],
                "source": job["source"],
                "job_hash": job["job_hash"],
            })
            continue

        # Step 2: Fast match
        fast_result = match_resume_fast(parsed_jd)
        score = fast_result["total_score"]

        # Step 3: AI match for strong candidates (if enabled)
        ai_result = None
        if use_ai and score >= ai_threshold:
            print(f"  🤖 [{i+1}/{len(jobs_with_desc)}] AI matching: {title} @ {company} (fast: {score})")
            ai_result = match_resume_ai(
                parsed_jd, job_title=title, company=company
            )
            score = ai_result.get("total_score", score)

        result = {
            "rank": 0,
            "title": title,
            "company": company,
            "location": job["location"],
            "url": job["url"],
            "h1b_score": job.get("h1b_score", 0),
            "match_score": score,
            "fit_tier": ai_result.get("fit_tier", fast_result["fit_tier"]) if ai_result else fast_result["fit_tier"],
            "strengths": ai_result.get("strengths", fast_result.get("strengths", [])) if ai_result else fast_result.get("strengths", []),
            "gaps": ai_result.get("gaps", fast_result.get("gaps", [])) if ai_result else fast_result.get("gaps", []),
            "cover_letter_angles": ai_result.get("cover_letter_angles", []) if ai_result else [],
            "source": job["source"],
            "job_hash": job["job_hash"],
        }
        results.append(result)
    
    # Save to database
    print("\n  💾 Saving match results to database...")
    saved = 0
    for r in results:
        r["combined_score"] = round(r["match_score"] * 0.6 + r["h1b_score"] * 0.4, 1)
        try:
            upsert_match_result(r)
            saved += 1
        except Exception:
            pass
    print(f"  ✅ Saved {saved} match results")
    # Sort by combined score (match + h1b)
    for r in results:
        r["combined_score"] = round(r["match_score"] * 0.6 + r["h1b_score"] * 0.4, 1)
    results.sort(key=lambda x: x["combined_score"], reverse=True)

    # Assign ranks
    for i, r in enumerate(results):
        r["rank"] = i + 1

    # Filter
    filtered = [r for r in results if r["match_score"] >= min_score]

    elapsed = time.time() - start
    print(f"\n⏱️  Matching completed in {elapsed:.1f}s")

    # Display
    print(f"\n{'=' * 60}")
    print(f"🏆 Top {min(top_n, len(filtered))} Matches (resume fit + H1B score)")
    print(f"{'=' * 60}")

    for r in filtered[:top_n]:
        print(f"\n  #{r['rank']} {r['fit_tier']}  Match: {r['match_score']}  |  H1B: {r['h1b_score']}  |  Combined: {r['combined_score']}")
        print(f"  📋 {r['title']}")
        print(f"  🏢 {r['company']} — 📍 {r['location']}")
        print(f"  🔗 {r['url'][:80]}")

        if r["strengths"]:
            print(f"  ✅ Strengths: {', '.join(r['strengths'][:3])}")
        if r["gaps"]:
            print(f"  ⚠️  Gaps: {', '.join(r['gaps'][:3])}")
        if r["cover_letter_angles"]:
            print(f"  💡 Cover letter: {r['cover_letter_angles'][0]}")

    # Summary stats
    strong = len([r for r in results if r["match_score"] >= 70])
    good = len([r for r in results if 50 <= r["match_score"] < 70])
    stretch = len([r for r in results if r["match_score"] < 50])

    print(f"\n{'─' * 60}")
    print(f"  📊 Match Summary:")
    print(f"     🟢 Strong (70+):  {strong} jobs")
    print(f"     🔵 Good (50-69):  {good} jobs")
    print(f"     🟡 Stretch (<50): {stretch} jobs")
    print(f"     Total matched:    {len(results)} jobs")

    return results


def export_results(results: list[dict], filename: str = "hawkapply_matches.csv"):
    """Export match results to CSV."""
    if not results:
        print("No results to export.")
        return

    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "rank", "title", "company", "location", "match_score",
            "h1b_score", "combined_score", "fit_tier", "source", "url",
        ], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"✅ Exported {len(results)} results to {filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HawkApply Resume Matcher")
    parser.add_argument("--ai", action="store_true", help="Use AI for deep matching on top candidates")
    parser.add_argument("--top", type=int, default=20, help="Show top N results")
    parser.add_argument("--min-score", type=float, default=0, help="Minimum match score")
    parser.add_argument("--ai-threshold", type=float, default=60, help="Score above which to use AI")
    parser.add_argument("--export", action="store_true", help="Export to CSV")

    args = parser.parse_args()

    results = run_matching(
        use_ai=args.ai,
        top_n=args.top,
        min_score=args.min_score,
        ai_threshold=args.ai_threshold,
    )

    if args.export:
        export_results(results)
