"""
Application Form Auto-Filler — generates ready-to-paste data for ATS platforms.

Reads your candidate_profile.json and formats it for each ATS type:
  - Greenhouse, Lever, Ashby (similar forms)
  - Workday (multi-step, most fields)
  - LinkedIn Easy Apply
  - Generic (covers most other platforms)

Also generates custom answers for common application questions
using GPT-4o-mini based on the job description.

Usage:
    python autofill.py                     # Generate profile for all ATS types
    python autofill.py --job-hash abc123   # Generate for specific job with custom answers
    python autofill.py --export            # Export all fields to JSON for browser extension
"""

import json
import argparse
from pathlib import Path
from typing import Optional
from openai import OpenAI
from config import settings
from parsers.resume_parser import load_profile, profile_exists
from db import operations as ops


client = OpenAI(api_key=settings.OPENAI_API_KEY)


def get_match_data(job_hash: str) -> dict:
    """Pull existing AI match data from database."""
    from db.operations import get_connection
    import json as _json

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT strengths, gaps, cover_letter_angles
                FROM match_results
                WHERE job_hash = %s;
            """, (job_hash,))
            row = cur.fetchone()

            if row:
                return {
                    "strengths": row[0] if isinstance(row[0], list) else _json.loads(row[0]) if row[0] else [],
                    "gaps": row[1] if isinstance(row[1], list) else _json.loads(row[1]) if row[1] else [],
                    "cover_letter_angles": row[2] if isinstance(row[2], list) else _json.loads(row[2]) if row[2] else [],
                }
    finally:
        conn.close()

    return {}

# ──────────────────────────────────────────────────
# Standard fields (same across all ATS platforms)
# ──────────────────────────────────────────────────

def build_standard_fields(profile: dict) -> dict:
    """Build standard application fields from profile."""
    
    # Most recent job
    current_job = profile.get("work_experience", [{}])[0] if profile.get("work_experience") else {}
    
    # Education
    latest_edu = profile.get("education", [{}])[0] if profile.get("education") else {}
    second_edu = profile.get("education", [{}])[1] if len(profile.get("education", [])) > 1 else {}

    return {
        # ── Personal Info ──
        "first_name": profile.get("name", "").split()[0] if profile.get("name") else "",
        "last_name": " ".join(profile.get("name", "").split()[1:]) if profile.get("name") else "",
        "full_name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "location": profile.get("location", ""),
        "city": profile.get("location", "").split(",")[0].strip() if profile.get("location") else "",
        "state": profile.get("location", "").split(",")[-1].strip() if "," in profile.get("location", "") else "",
        "country": "United States",
        "linkedin": profile.get("linkedin", ""),
        "github": profile.get("github", ""),
        "portfolio": profile.get("portfolio", ""),

        # ── Work Authorization ──
        "authorized_to_work_in_us": "Yes",
        "require_sponsorship": "Yes",
        "visa_status": profile.get("visa_status", "OPT STEM Extension"),
        "current_work_authorization": "OPT STEM Extension",
        "will_require_sponsorship_now_or_future": "Yes",

        # ── Current Employment ──
        "current_title": current_job.get("title", ""),
        "current_company": current_job.get("company", ""),
        "current_location": current_job.get("location", ""),
        "start_date": current_job.get("dates", "").split("-")[0].strip() if current_job.get("dates") else "",
        "years_experience": str(profile.get("years_experience", "")),

        # ── Education ──
        "degree_1": latest_edu.get("degree", ""),
        "school_1": latest_edu.get("school", ""),
        "graduation_1": latest_edu.get("graduation", ""),
        "gpa_1": str(latest_edu.get("gpa", "")) if latest_edu.get("gpa") else "",
        "degree_2": second_edu.get("degree", ""),
        "school_2": second_edu.get("school", ""),
        "graduation_2": second_edu.get("graduation", ""),

        # ── Skills Summary ──
        "programming_languages": ", ".join(profile.get("programming_languages", [])),
        "tools": ", ".join(profile.get("tools_and_platforms", [])),
        "skills_summary": ", ".join(
            profile.get("programming_languages", []) +
            profile.get("tools_and_platforms", []) +
            profile.get("ml_techniques", [])[:5]
        ),

        # ── Salary & Availability ──
        "desired_salary": "130000",
        "salary_currency": "USD",
        "available_start_date": "2 weeks notice",
        "willing_to_relocate": "Yes",
        "preferred_work_arrangement": "Hybrid or Remote",

        # ── Demographics (optional, usually skip) ──
        "gender": "Decline to self-identify",
        "race_ethnicity": "Decline to self-identify",
        "veteran_status": "I am not a protected veteran",
        "disability_status": "Decline to self-identify",

        # ── Source ──
        "how_did_you_hear": "Company career page",
    }


# ──────────────────────────────────────────────────
# ATS-specific formatters
# ──────────────────────────────────────────────────

def format_for_greenhouse(fields: dict, profile: dict) -> dict:
    """Format for Greenhouse application forms."""
    work_entries = []
    for exp in profile.get("work_experience", []):
        dates = exp.get("dates", "")
        parts = dates.replace("–", "-").split("-")
        start = parts[0].strip() if parts else ""
        end = parts[1].strip() if len(parts) > 1 else "Present"
        
        work_entries.append({
            "company": exp.get("company", ""),
            "title": exp.get("title", ""),
            "start_date": start,
            "end_date": end,
            "description": "\n".join(f"• {h}" for h in exp.get("highlights", [])),
        })

    return {
        **fields,
        "platform": "Greenhouse",
        "work_experience": work_entries,
        "cover_letter": "",  # Optional, filled by cover letter generator
        "resume": "Upload Shreya_Resume.pdf",
    }


def format_for_lever(fields: dict, profile: dict) -> dict:
    """Format for Lever application forms."""
    return {
        **fields,
        "platform": "Lever",
        "resume_text": _build_resume_text(profile),
        "additional_info": f"Currently on OPT STEM Extension. Will require H1B sponsorship. {fields['years_experience']} years of experience in data science.",
    }


def format_for_workday(fields: dict, profile: dict) -> dict:
    """Format for Workday (most detailed, multi-step)."""
    work_entries = []
    for exp in profile.get("work_experience", []):
        dates = exp.get("dates", "")
        parts = dates.replace("–", "-").split("-")
        start = parts[0].strip() if parts else ""
        end = parts[1].strip() if len(parts) > 1 else "Present"

        work_entries.append({
            "job_title": exp.get("title", ""),
            "company": exp.get("company", ""),
            "location": exp.get("location", ""),
            "from": start,
            "to": end,
            "currently_work_here": "Yes" if "present" in end.lower() else "No",
            "description": "\n".join(f"• {h}" for h in exp.get("highlights", [])),
        })

    edu_entries = []
    for edu in profile.get("education", []):
        edu_entries.append({
            "school": edu.get("school", ""),
            "degree": edu.get("degree", ""),
            "field_of_study": edu.get("degree", "").replace("Master's in ", "").replace("BS in ", ""),
            "gpa": str(edu.get("gpa", "")) if edu.get("gpa") else "",
            "graduation_date": edu.get("graduation", ""),
        })

    return {
        **fields,
        "platform": "Workday",
        "work_history": work_entries,
        "education_history": edu_entries,
        "address_line_1": "",
        "zip_code": "",
        "country_code": "US",
        "source": "Career Website",
        "legally_authorized": "Yes",
        "require_sponsorship_now_or_future": "Yes",
    }


def format_for_linkedin_easy_apply(fields: dict, profile: dict) -> dict:
    """Format for LinkedIn Easy Apply."""
    return {
        **fields,
        "platform": "LinkedIn Easy Apply",
        "headline": f"{fields['current_title']} at {fields['current_company']}",
        "summary": f"Data Scientist with {fields['years_experience']} years of experience in {', '.join(profile.get('domain_knowledge', [])[:3])}. Proficient in {fields['programming_languages']}.",
    }


def format_for_ashby(fields: dict, profile: dict) -> dict:
    """Format for Ashby (OpenAI, Anthropic, etc.)."""
    return {
        **fields,
        "platform": "Ashby",
        "resume": "Upload Shreya_Resume.pdf",
        "cover_letter": "",
        "linkedin_profile": fields["linkedin"],
    }


# ──────────────────────────────────────────────────
# Common application questions (GPT-powered)
# ──────────────────────────────────────────────────

COMMON_QUESTIONS = {
    "why_interested": "Why are you interested in this role?",
    "why_company": "Why do you want to work at {company}?",
    "greatest_strength": "What is your greatest strength?",
    "work_authorization": "Are you legally authorized to work in the United States?",
    "sponsorship": "Will you now or in the future require sponsorship?",
    "salary_expectations": "What are your salary expectations?",
    "start_date": "When can you start?",
    "relocation": "Are you willing to relocate?",
    "remote_preference": "What is your preferred work arrangement?",
    "years_of_experience": "How many years of relevant experience do you have?",
    "experience_with_python": "Describe your experience with Python.",
    "experience_with_ml": "Describe your experience with machine learning.",
}

ANSWER_PROMPT = """You are filling out a job application. Answer the question concisely and professionally.
Use the candidate's actual experience — don't make anything up.
Keep answers to 2-3 sentences unless it's a long-form question.
Mention specific projects, tools, and metrics from the candidate's experience.
Don't mention visa status unless the question specifically asks about it."""


def generate_custom_answers(
    job: dict,
    profile: dict,
    questions: list[str] = None,
    match_data: dict = None,
) -> dict:
    """Generate answers to custom application questions using GPT."""
    
    if not settings.OPENAI_API_KEY:
        return _default_answers(profile, job)

    if questions is None:
        questions = [
            f"Why are you interested in the {job.get('title', '')} role at {job.get('company', '')}?",
            "Describe your experience with data science and machine learning.",
            "What are your salary expectations?",
        ]

    answers = {}
    # Build context from existing match data
    match_context = ""
    if match_data:
        if match_data.get("strengths"):
            match_context += f"\nCandidate strengths for this role: {', '.join(match_data['strengths'][:3])}"
        if match_data.get("gaps"):
            match_context += f"\nGaps to address: {', '.join(match_data['gaps'][:3])}"
        if match_data.get("cover_letter_angles"):
            match_context += f"\nBest angles to highlight: {', '.join(match_data['cover_letter_angles'][:3])}"

    answers = {}
    for q in questions:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": ANSWER_PROMPT},
                    {"role": "user", "content": (
                        f"Question: {q}\n\n"
                        f"Job: {job.get('title', '')} at {job.get('company', '')}\n"
                        f"Job Description: {job.get('description', '')[:1000]}\n\n"
                        f"Candidate Profile:\n{json.dumps(profile, indent=2)}"
                        f"{match_context}"
                    )},
                ],
                temperature=0.3,
                max_tokens=300,
            )
            answers[q] = response.choices[0].message.content.strip()
        except Exception as e:
            answers[q] = _default_answer(q, profile, job)

    return answers


def _default_answers(profile: dict, job: dict) -> dict:
    """Fallback answers without API."""
    company = job.get("company", "the company")
    title = job.get("title", "this role")
    yrs = profile.get("years_experience", 4)
    langs = ", ".join(profile.get("programming_languages", []))
    tools = ", ".join(profile.get("tools_and_platforms", [])[:4])
    
    return {
        "Why are you interested in this role?": f"With {yrs} years of experience in data science, I'm excited about the {title} position because it aligns with my expertise in {langs} and {tools}. My current work at {profile.get('work_experience', [{}])[0].get('company', 'my current company')} has given me hands-on experience that directly applies to this role.",
        "Describe your experience with data science.": f"I have {yrs} years of experience across data science and analytics roles. Currently as a Data Scientist at {profile.get('work_experience', [{}])[0].get('company', '')}, I build predictive models, design A/B tests, and architect data pipelines using {langs} and {tools}.",
        "Salary expectations": "My target compensation is $130,000-$160,000, depending on the total compensation package including benefits and equity.",
        "Are you authorized to work in the US?": "Yes",
        "Will you require sponsorship?": "Yes, I will require H1B sponsorship.",
        "When can you start?": "I can start within 2 weeks of accepting an offer.",
        "Willing to relocate?": "Yes",
    }


def _default_answer(question: str, profile: dict, job: dict) -> str:
    q = question.lower()
    if "salary" in q:
        return "$130,000 - $160,000"
    elif "authorized" in q:
        return "Yes"
    elif "sponsor" in q:
        return "Yes"
    elif "start" in q:
        return "2 weeks notice"
    elif "relocate" in q:
        return "Yes"
    elif "experience" in q and "year" in q:
        return str(profile.get("years_experience", 4))
    return ""


# ──────────────────────────────────────────────────
# Resume text builder (for platforms that want plain text)
# ──────────────────────────────────────────────────

def _build_resume_text(profile: dict) -> str:
    """Build a plain-text resume from profile."""
    lines = []
    lines.append(profile.get("name", ""))
    lines.append(f"{profile.get('email', '')} | {profile.get('location', '')}")
    lines.append("")
    
    lines.append("EXPERIENCE")
    for exp in profile.get("work_experience", []):
        lines.append(f"{exp.get('title', '')} | {exp.get('company', '')} | {exp.get('dates', '')}")
        for h in exp.get("highlights", []):
            lines.append(f"  • {h}")
        lines.append("")
    
    lines.append("EDUCATION")
    for edu in profile.get("education", []):
        gpa = f" | GPA: {edu['gpa']}" if edu.get("gpa") else ""
        lines.append(f"{edu.get('degree', '')} | {edu.get('school', '')}{gpa} | {edu.get('graduation', '')}")
    lines.append("")
    
    lines.append("SKILLS")
    lines.append(f"Languages: {', '.join(profile.get('programming_languages', []))}")
    lines.append(f"Tools: {', '.join(profile.get('tools_and_platforms', []))}")
    lines.append(f"ML: {', '.join(profile.get('ml_techniques', [])[:8])}")
    
    return "\n".join(lines)


# ──────────────────────────────────────────────────
# Export for browser extension / clipboard
# ──────────────────────────────────────────────────

def export_autofill(profile: dict, job: dict = None, output_path: str = None, match_data: dict = None) -> dict:
    """Export all autofill data as JSON for browser extension or clipboard."""
    
    fields = build_standard_fields(profile)
    
    result = {
        "standard_fields": fields,
        "greenhouse": format_for_greenhouse(fields, profile),
        "lever": format_for_lever(fields, profile),
        "workday": format_for_workday(fields, profile),
        "linkedin": format_for_linkedin_easy_apply(fields, profile),
        "ashby": format_for_ashby(fields, profile),
    }
    
    if job:
        result["custom_answers"] = generate_custom_answers(job, profile, match_data=match_data)
        if match_data:
            result["match_data"] = match_data
        result["job_info"] = {
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "url": job.get("url", ""),
        }
    
    if output_path:
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"  ✅ Exported to {output_path}")
    
    return result


# ──────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HawkApply Auto-Filler")
    parser.add_argument("--job-hash", type=str, help="Generate for specific job")
    parser.add_argument("--export", action="store_true", help="Export to JSON")
    parser.add_argument("--all-reviewing", action="store_true", help="Generate for all reviewing jobs")
    parser.add_argument("--pick", action="store_true", help="Interactively pick a job to autofill")
    args = parser.parse_args()

    if not profile_exists():
        print("❌ No resume parsed. Run: python -m parsers.resume_parser path/to/resume.pdf")
        return

    profile = load_profile()
    fields = build_standard_fields(profile)

    print("=" * 60)
    print("📝 HawkApply — Application Auto-Filler")
    print("=" * 60)

    if args.job_hash:
        # Generate for specific job
        jobs = ops.get_jobs(limit=500)
        job = next((j for j in jobs if j["job_hash"] == args.job_hash), None)
        if not job:
            print(f"❌ Job {args.job_hash} not found")
            return

        print(f"\n  📋 {job['title']} @ {job['company']}")
        print(f"  🔗 {job['url']}")

        # Detect ATS from URL
        ats = _detect_ats(job["url"])
        print(f"  🏢 Detected ATS: {ats}")

        if ats == "Greenhouse":
            data = format_for_greenhouse(fields, profile)
        elif ats == "Lever":
            data = format_for_lever(fields, profile)
        elif ats == "Workday":
            data = format_for_workday(fields, profile)
        elif ats == "Ashby":
            data = format_for_ashby(fields, profile)
        else:
            data = fields

        # Generate custom answers
        # Pull existing match data
        match_data = get_match_data(args.job_hash)
        has_match_data = any([
            match_data.get("strengths"),
            match_data.get("gaps"),
            match_data.get("cover_letter_angles"),
        ])

        if has_match_data:
            print("  📦 Using existing AI match data...")
            answers = generate_custom_answers(job, profile, match_data=match_data)
        else:
            print("  🤖 No match data found (run match_jobs.py --ai first)...")
            answers = generate_custom_answers(job, profile)

        print(f"\n  {'─' * 50}")
        print(f"  📋 Auto-fill data for {ats}:")
        for key, value in data.items():
            if isinstance(value, (list, dict)):
                continue
            if value:
                print(f"    {key}: {value}")

        print(f"\n  💬 Custom answers:")
        for q, a in answers.items():
            print(f"\n    Q: {q}")
            print(f"    A: {a}")

        if args.export:
            result = export_autofill(profile, job, f"data/autofill_{args.job_hash}.json")

    elif args.all_reviewing:
        # Generate for all reviewing jobs
        jobs = ops.get_jobs(status="reviewing", limit=100)
        if not jobs:
            print("  No jobs in 'reviewing' status. Run review_jobs.py first.")
            return

        print(f"\n  Generating autofill for {len(jobs)} reviewing jobs...")
        for job in jobs:
            ats = _detect_ats(job["url"])
            match_data = get_match_data(job["job_hash"])
            has_match = bool(match_data.get("strengths") or match_data.get("gaps"))
            print(f"\n  📋 {job['title']} @ {job['company']} ({ats}) {'📦 has match data' if has_match else '⚠️ no match data'}")
            result = export_autofill(profile, job, f"data/autofill_{job['job_hash']}.json", match_data=match_data)
    elif args.pick:
        jobs = ops.get_jobs(status="reviewing", limit=50)
        if not jobs:
            print("  No reviewing jobs. Run review_jobs.py first.")
            return

        print("\n  Pick a job to autofill:\n")
        for i, job in enumerate(jobs):
            print(f"    [{i+1}] {job['title']} @ {job['company']}")

        choice = input("\n  Enter number: ").strip()
        try:
            job = jobs[int(choice) - 1]
        except (ValueError, IndexError):
            print("  Invalid choice")
            return

        print(f"\n  Selected: {job['title']} @ {job['company']}")
        print(f"  🔗 {job['url']}")

        ats = _detect_ats(job["url"])
        print(f"  🏢 Detected ATS: {ats}")

        if ats == "Greenhouse":
            data = format_for_greenhouse(fields, profile)
        elif ats == "Lever":
            data = format_for_lever(fields, profile)
        elif ats == "Workday":
            data = format_for_workday(fields, profile)
        elif ats == "Ashby":
            data = format_for_ashby(fields, profile)
        else:
            data = fields

        match_data = get_match_data(job["job_hash"])
        has_match_data = any([
            match_data.get("strengths"),
            match_data.get("gaps"),
            match_data.get("cover_letter_angles"),
        ])

        if has_match_data:
            print("  📦 Using existing AI match data...")
            answers = generate_custom_answers(job, profile, match_data=match_data)
        else:
            print("  🤖 No match data found (run match_jobs.py --ai first)...")
            answers = generate_custom_answers(job, profile)

        print(f"\n  {'─' * 50}")
        print(f"  📋 Auto-fill data for {ats}:")
        for key, value in data.items():
            if isinstance(value, (list, dict)):
                continue
            if value:
                print(f"    {key}: {value}")

        print(f"\n  💬 Custom answers:")
        for q, a in answers.items():
            print(f"\n    Q: {q}")
            print(f"    A: {a}")

        export_autofill(profile, job, f"data/autofill_{job['job_hash']}.json", match_data=match_data)

    else:
        # Show standard profile
        print(f"\n  👤 {fields['full_name']}")
        print(f"  📧 {fields['email']}")
        print(f"  📍 {fields['location']}")
        print(f"  💼 {fields['current_title']} @ {fields['current_company']}")
        print(f"  🎓 {fields['degree_1']} — {fields['school_1']}")
        print(f"  💻 {fields['programming_languages']}")
        print(f"  🏛️  Sponsorship: {fields['require_sponsorship']}")
        print(f"  💰 Target salary: ${fields['desired_salary']}")

        print(f"\n  {'─' * 50}")
        print("  Standard answers:")
        print(f"    Authorized to work in US: {fields['authorized_to_work_in_us']}")
        print(f"    Require sponsorship: {fields['require_sponsorship']}")
        print(f"    Years experience: {fields['years_experience']}")
        print(f"    Available: {fields['available_start_date']}")
        print(f"    Willing to relocate: {fields['willing_to_relocate']}")

        if args.export:
            export_autofill(profile, output_path="data/autofill_profile.json")
            print("\n  💡 Use data/autofill_profile.json with a browser extension to auto-fill forms")


def _detect_ats(url: str) -> str:
    """Detect ATS platform from job URL."""
    url = url.lower()
    if "greenhouse.io" in url or "boards.greenhouse" in url or "gh_jid" in url:
        return "Greenhouse"
    elif "lever.co" in url or "jobs.lever" in url:
        return "Lever"
    elif "myworkdayjobs.com" in url or "workday" in url:
        return "Workday"
    elif "ashbyhq.com" in url:
        return "Ashby"
    elif "smartrecruiters.com" in url:
        return "SmartRecruiters"
    elif "linkedin.com" in url:
        return "LinkedIn"
    elif "indeed.com" in url:
        return "Indeed"
    return "Generic"


if __name__ == "__main__":
    main()
