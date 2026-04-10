"""
Resume Matcher — scores how well a candidate matches a parsed job description.

Takes:
  - Parsed JD (from jd_parser.py)
  - Candidate profile (from resume)

Returns:
  - Overall match score (0-100)
  - Skill-by-skill breakdown
  - Gaps to address in cover letter
  - Strengths to highlight

Usage:
    from parsers.resume_matcher import match_resume, SHREYA_PROFILE
    result = match_resume(parsed_jd, SHREYA_PROFILE)
"""

import json
from typing import Optional
from openai import OpenAI
from config import settings
from parsers.resume_parser import load_profile, profile_exists

client = OpenAI(api_key=settings.OPENAI_API_KEY)


# ──────────────────────────────────────────────────
# Candidate profile — extracted from Shreya's resume
# Update this when the resume changes
# ──────────────────────────────────────────────────

# SHREYA_PROFILE = {
#     "name": "Shreya Sahay",
#     "email": "sh10findit@gmail.com",
#     "location": "New York City, NY",
#     "visa_status": "OPT STEM Extension (H1B sponsorship needed)",

#     "education": [
#         {
#             "degree": "Master's in Data Science",
#             "school": "George Washington University",
#             "location": "Washington, DC",
#             "gpa": 3.97,
#             "graduation": "May 2025",
#         },
#         {
#             "degree": "BS in Electronics & Telecommunication Engineering",
#             "school": "Kalinga Institute of Industrial Technology",
#             "location": "Bhubaneswar, India",
#             "graduation": "May 2021",
#         },
#     ],

#     "years_experience": 4,  # Total professional experience

#     "programming_languages": [
#         "python", "pyspark", "sql",
#     ],

#     "tools_and_platforms": [
#         "databricks", "aws", "ec2", "s3", "gcp",
#         "tableau", "dbt", "airflow",
#     ],

#     "ml_techniques": [
#         "logistic regression", "random forest", "xgboost",
#         "linear regression", "clustering", "classification",
#         "bayesian modeling", "hypothesis testing",
#         "a/b testing", "regression analysis",
#         "k-fold cross-validation", "hyperparameter tuning",
#         "feature engineering", "statistical experimentation",
#     ],

#     "domain_knowledge": [
#         "marketing analytics", "media", "advertising",
#         "viewer retention", "attribution analysis",
#         "campaign measurement", "ad exposure",
#         "financial banking", "insurance",
#         "peacekeeping operations", "international development",
#         "risk assessment", "underwriting",
#     ],

#     "soft_skills": [
#         "cross-functional collaboration",
#         "stakeholder communication",
#         "presentation", "visualization dashboards",
#     ],

#     "work_experience": [
#         {
#             "title": "Data Scientist",
#             "company": "Optimum Media",
#             "location": "New York City, NY",
#             "dates": "Jun 2025 – Present",
#             "highlights": [
#                 "Viewer retention scoring using logistic regression",
#                 "Attribution analysis linking ad exposure to tune-in behavior",
#                 "End-to-end data pipelines in Databricks using PySpark",
#                 "CI/CD configuration, job orchestration, monitoring",
#                 "A/B tests and controlled experiments for campaign impact",
#             ],
#         },
#         {
#             "title": "Data Fellow – Capstone Project",
#             "company": "World Bank",
#             "location": "Washington, DC",
#             "dates": "Jan 2025 – May 2025",
#             "highlights": [
#                 "Statistical modeling and ML to predict cost overruns",
#                 "Analysis of 150+ World Bank funded projects",
#             ],
#         },
#         {
#             "title": "Data Science Intern",
#             "company": "United Nations",
#             "location": "New York City, NY",
#             "dates": "Jul 2024 – Dec 2024",
#             "highlights": [
#                 "Data pipelines in Python and SQL",
#                 "Predictive models (Linear Regression, Random Forest, XGBoost)",
#                 "k-fold cross-validation and hyperparameter tuning",
#                 "Forecasting for resource allocation in peacekeeping",
#             ],
#         },
#         {
#             "title": "Senior Data Analyst",
#             "company": "KPMG",
#             "location": "Gurugram, India",
#             "dates": "Sep 2022 – Jul 2023",
#             "highlights": [
#                 "1.5 million financial banking customer records",
#                 "ML techniques for customer segmentation and cohort analysis",
#                 "CI/CD pipelines, real-time model performance monitoring",
#                 "ETL pipelines using dbt with Airflow orchestration",
#                 "Tableau dashboards for senior leadership",
#             ],
#         },
#         {
#             "title": "Data Analyst",
#             "company": "Capgemini",
#             "location": "Kolkata, India",
#             "dates": "Jan 2021 – Aug 2022",
#             "highlights": [
#                 "Insurance claims and quotes data processing",
#                 "Risk-related insights and pattern detection",
#                 "EDA and statistical profiling for anomaly detection",
#             ],
#         },
#     ],
# }
def get_profile() -> dict:
    """Load candidate profile from parsed resume PDF."""
    if profile_exists():
        return load_profile()
    print("  ⚠️  No resume parsed yet. Run: python -m parsers.resume_parser path/to/resume.pdf")
    return {
        "name": "", "email": "", "location": "", "visa_status": "unknown",
        "education": [], "years_experience": 0, "programming_languages": [],
        "tools_and_platforms": [], "ml_techniques": [], "domain_knowledge": [],
        "soft_skills": [], "work_experience": [],
    }

# ──────────────────────────────────────────────────
# Rule-based matcher (fast, no API call)
# ──────────────────────────────────────────────────

def match_resume_fast(parsed_jd: dict, profile: dict = None) -> dict:
    """
    Fast rule-based matching. No API call needed.
    Returns score + breakdown without using OpenAI.
    """
    if profile is None:
        # profile = SHREYA_PROFILE
        profile = get_profile()
    

    scores = {}
    details = {}

    # 1. Programming languages (20 pts)
    jd_langs = set(s.lower() for s in parsed_jd.get("programming_languages", []))
    my_langs = set(s.lower() for s in profile["programming_languages"])
    if jd_langs:
        matched = jd_langs & my_langs
        missing = jd_langs - my_langs
        scores["languages"] = round(len(matched) / len(jd_langs) * 20, 1)
        details["languages"] = {"matched": list(matched), "missing": list(missing)}
    else:
        scores["languages"] = 20
        details["languages"] = {"matched": [], "missing": []}

    # 2. Tools & platforms (20 pts)
    jd_tools = set(s.lower() for s in parsed_jd.get("tools_and_platforms", []))
    my_tools = set(s.lower() for s in profile["tools_and_platforms"])
    if jd_tools:
        matched = jd_tools & my_tools
        # Fuzzy: check if any of my tools are substrings of JD tools or vice versa
        for jt in list(jd_tools - matched):
            for mt in my_tools:
                if mt in jt or jt in mt:
                    matched.add(jt)
                    break
        missing = jd_tools - matched
        scores["tools"] = round(len(matched) / len(jd_tools) * 20, 1)
        details["tools"] = {"matched": list(matched), "missing": list(missing)}
    else:
        scores["tools"] = 20
        details["tools"] = {"matched": [], "missing": []}

    # 3. ML techniques (20 pts)
    jd_ml = set(s.lower() for s in parsed_jd.get("ml_techniques", []))
    my_ml = set(s.lower() for s in profile["ml_techniques"])
    if jd_ml:
        matched = set()
        for jm in jd_ml:
            for mm in my_ml:
                if mm in jm or jm in mm:
                    matched.add(jm)
                    break
        missing = jd_ml - matched
        scores["ml_techniques"] = round(len(matched) / len(jd_ml) * 20, 1)
        details["ml_techniques"] = {"matched": list(matched), "missing": list(missing)}
    else:
        scores["ml_techniques"] = 15
        details["ml_techniques"] = {"matched": [], "missing": []}

    # 4. Experience level (15 pts)
    jd_min_yrs = parsed_jd.get("years_experience_min", -1)
    my_yrs = profile["years_experience"]
    if jd_min_yrs <= 0:
        scores["experience"] = 12
    elif my_yrs >= jd_min_yrs:
        scores["experience"] = 15
    elif my_yrs >= jd_min_yrs - 1:
        scores["experience"] = 10  # Close enough
    else:
        scores["experience"] = 5
    details["experience"] = {
        "required": jd_min_yrs,
        "candidate_has": my_yrs,
    }

    # 5. Education (10 pts)
    jd_edu = parsed_jd.get("education", {})
    jd_degree = jd_edu.get("degree", "").lower()
    has_masters = any("master" in e["degree"].lower() for e in profile["education"])
    if "phd" in jd_degree or "doctorate" in jd_degree:
        scores["education"] = 5  # We have Masters, not PhD
    elif "master" in jd_degree and has_masters:
        scores["education"] = 10
    elif "bachelor" in jd_degree:
        scores["education"] = 10
    else:
        scores["education"] = 8
    details["education"] = {
        "required": jd_degree or "not specified",
        "candidate_has": "Master's in Data Science (GPA 3.97)",
    }

    # 6. Domain knowledge (15 pts)
    jd_domains = set(s.lower() for s in parsed_jd.get("domain_knowledge", []))
    my_domains = set(s.lower() for s in profile["domain_knowledge"])
    if jd_domains:
        matched = set()
        for jd in jd_domains:
            for md in my_domains:
                if md in jd or jd in md:
                    matched.add(jd)
                    break
        missing = jd_domains - matched
        scores["domain"] = round(len(matched) / len(jd_domains) * 15, 1)
        details["domain"] = {"matched": list(matched), "missing": list(missing)}
    else:
        scores["domain"] = 10
        details["domain"] = {"matched": [], "missing": []}

    # Total
    total = round(sum(scores.values()), 1)

    # Identify strengths and gaps
    strengths = []
    gaps = []

    for category, detail in details.items():
        if isinstance(detail, dict) and "matched" in detail:
            if detail["matched"]:
                strengths.extend(detail["matched"])
            if detail.get("missing"):
                gaps.extend(detail["missing"])

    return {
        "total_score": total,
        "max_score": 100,
        "scores": scores,
        "details": details,
        "strengths": strengths[:10],
        "gaps": gaps[:10],
        "fit_tier": _score_tier(total),
    }


# ──────────────────────────────────────────────────
# AI-powered matcher (deeper analysis, costs ~$0.001)
# ──────────────────────────────────────────────────

MATCH_PROMPT = """You are a job application strategist. Compare the candidate's profile against the job requirements.

Return ONLY valid JSON (no markdown, no backticks):
{
    "total_score": 78,
    "fit_tier": "Strong Match",
    "strengths": [
        "Direct experience with PySpark and Databricks matches JD requirements",
        "Marketing analytics background aligns with the team's focus"
    ],
    "gaps": [
        "JD requires PyTorch experience — candidate has sklearn/XGBoost but not deep learning frameworks",
        "3 years required but candidate has ~2 years in pure DS roles"
    ],
    "cover_letter_angles": [
        "Lead with Optimum Media viewer retention work — directly relevant to this role's audience analytics focus",
        "Highlight UN forecasting project as evidence of production ML work",
        "Address the PyTorch gap by mentioning willingness to learn and strong ML fundamentals"
    ],
    "resume_tweaks": [
        "Move the A/B testing bullet higher since the JD emphasizes experimentation",
        "Add specific model metrics (AUC, lift %) to quantify impact"
    ],
    "interview_prep": [
        "Be ready to discuss attribution modeling methodology",
        "Prepare a case study on viewer retention scoring at Optimum Media"
    ]
}

Score on a 0-100 scale:
- 80+ = Strong Match (apply immediately)
- 60-79 = Good Match (apply with targeted cover letter)
- 40-59 = Stretch (address gaps explicitly)
- Below 40 = Poor fit (skip unless dream company)"""


def match_resume_ai(parsed_jd: dict, profile: dict = None,
                    job_title: str = "", company: str = "") -> dict:
    """
    AI-powered deep matching using GPT-4o-mini.
    Costs ~$0.001 per call. Use for top candidates only.
    """
    if profile is None:
        # profile = SHREYA_PROFILE
        profile = get_profile()

    if not settings.OPENAI_API_KEY:
        print("  ⚠️  No OPENAI_API_KEY — falling back to rule-based matching")
        return match_resume_fast(parsed_jd, profile)

    context = f"Job: {job_title} at {company}\n" if job_title else ""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": MATCH_PROMPT},
                {"role": "user", "content": (
                    f"{context}\n"
                    f"JOB REQUIREMENTS:\n{json.dumps(parsed_jd, indent=2)}\n\n"
                    f"CANDIDATE PROFILE:\n{json.dumps(profile, indent=2)}"
                )},
            ],
            temperature=0.2,
            max_tokens=1000,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        result = json.loads(raw.strip())

        # Ensure all keys exist
        for key in ["total_score", "fit_tier", "strengths", "gaps",
                     "cover_letter_angles", "resume_tweaks", "interview_prep"]:
            if key not in result:
                result[key] = [] if key != "total_score" and key != "fit_tier" else 0

        return result

    except Exception as e:
        print(f"  ⚠️  AI match failed: {e}, falling back to rule-based")
        return match_resume_fast(parsed_jd, profile)


# ──────────────────────────────────────────────────
# Combined matcher — fast first, AI for top matches
# ──────────────────────────────────────────────────

def match_resume(parsed_jd: dict, profile: dict = None,
                 job_title: str = "", company: str = "",
                 use_ai: bool = False) -> dict:
    """
    Match resume against parsed JD.
    
    Default: fast rule-based matching.
    Set use_ai=True for deep AI analysis (costs ~$0.001).
    """
    if use_ai:
        return match_resume_ai(parsed_jd, profile, job_title, company)
    return match_resume_fast(parsed_jd, profile)


def match_jobs_batch(jobs_with_jds: list[tuple[dict, dict]],
                     ai_threshold: float = 60.0) -> list[dict]:
    """
    Match a batch of jobs. Uses fast matching for all,
    then AI matching for jobs scoring above the threshold.
    
    Args:
        jobs_with_jds: List of (job_dict, parsed_jd) tuples
        ai_threshold: Score above which to run AI matcher
    
    Returns:
        List of match results with job info
    """
    results = []

    for job, parsed_jd in jobs_with_jds:
        # Fast match first
        fast_result = match_resume_fast(parsed_jd)
        
        result = {
            "job_hash": job.get("job_hash", ""),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "url": job.get("url", ""),
            "fast_score": fast_result["total_score"],
            "fast_result": fast_result,
            "ai_result": None,
        }

        # AI match for strong candidates
        if fast_result["total_score"] >= ai_threshold:
            print(f"  🤖 AI matching: {job.get('title', '')} @ {job.get('company', '')} (fast score: {fast_result['total_score']})")
            ai_result = match_resume_ai(
                parsed_jd,
                job_title=job.get("title", ""),
                company=job.get("company", ""),
            )
            result["ai_result"] = ai_result
            result["final_score"] = ai_result.get("total_score", fast_result["total_score"])
        else:
            result["final_score"] = fast_result["total_score"]

        results.append(result)

    # Sort by final score
    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results


def _score_tier(score: float) -> str:
    if score >= 80:
        return "🟢 Strong Match"
    elif score >= 60:
        return "🔵 Good Match"
    elif score >= 40:
        return "🟡 Stretch"
    return "🔴 Poor Fit"


if __name__ == "__main__":
    # Quick test with a sample parsed JD
    sample_jd = {
        "required_skills": ["python", "sql", "machine learning", "a/b testing"],
        "preferred_skills": ["pytorch", "causal inference"],
        "programming_languages": ["python", "sql", "pyspark"],
        "tools_and_platforms": ["databricks", "aws", "tableau"],
        "ml_techniques": ["logistic regression", "xgboost", "a/b testing"],
        "years_experience_min": 3,
        "education": {"degree": "masters", "fields": ["data science", "statistics"]},
        "domain_knowledge": ["marketing", "advertising"],
        "soft_skills": ["communication", "stakeholder management"],
        "visa_sponsorship": "yes",
    }

    print("=== Fast Match ===")
    fast = match_resume_fast(sample_jd)
    print(f"Score: {fast['total_score']}/100 — {fast['fit_tier']}")
    print(f"Strengths: {fast['strengths'][:5]}")
    print(f"Gaps: {fast['gaps'][:5]}")

    print("\n=== AI Match ===")
    ai = match_resume_ai(sample_jd, job_title="Data Scientist", company="Netflix")
    print(json.dumps(ai, indent=2))
