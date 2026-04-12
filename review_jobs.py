"""
Review matched jobs and provide feedback for RLHF.

Usage:
    python review_jobs.py              # Review top matches interactively
    python review_jobs.py --export     # Export for manual review in spreadsheet
"""

import json
from db import operations as ops
from db.operations import get_connection


def review_interactive(limit: int = 50):
    """Interactive review of top matched jobs."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT m.*, j.title, j.company, j.location, j.url, j.description
            FROM match_results m
            JOIN jobs j ON j.job_hash = m.job_hash
            ORDER BY m.combined_score DESC
            LIMIT %s;
        """, (limit,))
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    conn.close()

    if not rows:
        print("No match results found. Run match_jobs.py first.")
        return

    print("=" * 60)
    print("📝 HawkApply — Job Review (RLHF Feedback)")
    print("=" * 60)
    print("For each job, rate the match quality:")
    print("  5 = Perfect match, applying immediately")
    print("  4 = Good match, will apply")
    print("  3 = Decent, might apply")
    print("  2 = Poor match, wrong scoring")
    print("  1 = Terrible match, should not have shown")
    print("  s = Skip")
    print("  q = Quit")
    print()

    feedback = []

    for i, row in enumerate(rows):
        print(f"\n{'─' * 60}")
        print(f"  [{i+1}/{len(rows)}] Score: {row.get('combined_score', 0)}")
        print(f"  📋 {row['title']}")
        print(f"  🏢 {row['company']} — 📍 {row['location']}")
        print(f"  🔗 {row['url']}")

        strengths = json.loads(row.get('strengths', '[]')) if isinstance(row.get('strengths'), str) else row.get('strengths', [])
        gaps = json.loads(row.get('gaps', '[]')) if isinstance(row.get('gaps'), str) else row.get('gaps', [])

        if strengths:
            print(f"  ✅ {', '.join(strengths[:3])}")
        if gaps:
            print(f"  ⚠️  {', '.join(gaps[:3])}")

        rating = input("\n  Your rating (1-5/s/q): ").strip().lower()

        if rating == 'q':
            break
        elif rating == 's':
            continue
        elif rating in ['1', '2', '3', '4', '5']:
            notes = ""
            if int(rating) <= 2:
                notes = input("  Why is this a bad match? ").strip()
            elif int(rating) >= 4:
                notes = input("  What makes this a good match? (optional) ").strip()

            feedback.append({
                "job_hash": row.get("job_hash", ""),
                "title": row["title"],
                "company": row["company"],
                "system_score": row.get("combined_score", 0),
                "user_rating": int(rating),
                "notes": notes,
            })

            # Save to database
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO applications (job_id, user_rating, feedback_notes)
                    SELECT j.id, %s, %s
                    FROM jobs j WHERE j.job_hash = %s
                    ON CONFLICT DO NOTHING;
                """, (int(rating), notes, row.get("job_hash", "")))

                # Mark job status based on rating
                if int(rating) >= 4:
                    cur.execute(
                        "UPDATE jobs SET status = 'reviewing' WHERE job_hash = %s;",
                        (row.get("job_hash", ""),)
                    )
                elif int(rating) <= 2:
                    cur.execute(
                        "UPDATE jobs SET status = 'rejected' WHERE job_hash = %s;",
                        (row.get("job_hash", ""),)
                    )
                conn.commit()
            conn.close()

    # Summary
    if feedback:
        avg_rating = sum(f["user_rating"] for f in feedback) / len(feedback)
        mismatches = [f for f in feedback if abs(f["system_score"] - f["user_rating"] * 20) > 30]

        print(f"\n{'=' * 60}")
        print(f"📊 Review Summary:")
        print(f"   Reviewed: {len(feedback)} jobs")
        print(f"   Avg rating: {avg_rating:.1f}/5")
        print(f"   Score mismatches: {len(mismatches)}")

        if mismatches:
            print(f"\n   ⚠️  These jobs had wrong scores:")
            for m in mismatches:
                print(f"      {m['title']} @ {m['company']}: system={m['system_score']}, you={m['user_rating']}/5")

        # Save feedback for RLHF training
        with open("data/rlhf_feedback.json", "a") as f:
            for fb in feedback:
                f.write(json.dumps(fb) + "\n")
        print(f"\n   💾 Feedback saved to data/rlhf_feedback.json")
        print(f"   📈 This data will improve matching over time")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    review_interactive(limit=args.limit)