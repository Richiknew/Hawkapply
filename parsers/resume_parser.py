"""
Resume Parser — reads a PDF resume and extracts a structured candidate profile.

Uses PyPDF2 to extract text, then GPT-4o-mini to parse into structured format.
The output profile is used by resume_matcher.py and cover_letter_generator.

Usage:
    from parsers.resume_parser import parse_resume, load_profile
    
    # First time: parse PDF and save profile
    profile = parse_resume("path/to/resume.pdf")
    
    # Subsequent runs: load cached profile
    profile = load_profile()
"""

import json
import re
from pathlib import Path
from typing import Optional
from openai import OpenAI
from config import settings


client = OpenAI(api_key=settings.OPENAI_API_KEY)

PROFILE_PATH = Path(settings.DATA_DIR) / "candidate_profile.json"


PARSE_PROMPT = """You are a resume parser. Extract structured information from the following resume text.

Return ONLY valid JSON (no markdown, no backticks) with this exact schema:
{
    "name": "Full Name",
    "email": "email@example.com",
    "phone": "phone number or empty string",
    "location": "City, State",
    "linkedin": "linkedin url or empty string",
    "github": "github url or empty string",
    "portfolio": "portfolio url or empty string",
    "visa_status": "OPT/H1B/Green Card/US Citizen/unknown",
    
    "education": [
        {
            "degree": "Master's in Data Science",
            "school": "University Name",
            "location": "City, State",
            "gpa": 3.97,
            "graduation": "May 2025"
        }
    ],
    
    "years_experience": 4,
    
    "programming_languages": ["python", "sql", "pyspark"],
    
    "tools_and_platforms": ["databricks", "aws", "tableau"],
    
    "ml_techniques": ["logistic regression", "random forest", "a/b testing"],
    
    "domain_knowledge": ["marketing analytics", "finance", "insurance"],
    
    "soft_skills": ["cross-functional collaboration", "stakeholder communication"],
    
    "certifications": ["AWS Certified", "Databricks Certified"],
    
    "work_experience": [
        {
            "title": "Data Scientist",
            "company": "Company Name",
            "location": "City, State",
            "dates": "Jun 2025 - Present",
            "highlights": [
                "Built viewer retention model using logistic regression, achieving AUC of 0.85",
                "Designed A/B tests measuring incremental campaign impact"
            ]
        }
    ]
}

Rules:
- Extract ALL skills mentioned anywhere in the resume
- Keep skills lowercase
- For years_experience, calculate total from work experience dates
- Include ALL work experience entries, not just the most recent
- Extract specific metrics and numbers from bullet points
- For visa_status, infer from context (international university, OPT mention, etc.) or set "unknown"
- GPA should be a number, not a string. Use null if not mentioned."""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF resume."""
    try:
        import PyPDF2
        text = ""
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text.strip()
    except ImportError:
        print("  ⚠️  PyPDF2 not installed. Run: pip install PyPDF2")
        raise
    except Exception as e:
        print(f"  ⚠️  Failed to read PDF: {e}")
        raise


def parse_resume(pdf_path: str, save: bool = True) -> dict:
    """
    Parse a PDF resume into a structured candidate profile.
    
    Args:
        pdf_path: Path to the PDF resume file
        save: Whether to save the profile to disk for reuse
    
    Returns:
        Structured profile dict
    """
    print(f"📄 Reading resume: {pdf_path}")
    resume_text = extract_text_from_pdf(pdf_path)

    if not resume_text:
        print("  ❌ No text extracted from PDF")
        return {}

    print(f"  📝 Extracted {len(resume_text)} characters")
    print(f"  🤖 Parsing with GPT-4o-mini...")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PARSE_PROMPT},
                {"role": "user", "content": f"Resume:\n{resume_text[:6000]}"},
            ],
            temperature=0.1,
            max_tokens=2000,
        )

        raw = response.choices[0].message.content.strip()
        # Clean markdown wrapping
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        profile = json.loads(raw)
        profile = _validate_profile(profile)

        if save:
            _save_profile(profile)
            print(f"  ✅ Profile saved to {PROFILE_PATH}")
        #if profile.get("visa_status", "unknown") == "unknown":
        profile["visa_status"] = "OPT STEM Extension (H1B sponsorship needed)"

        _print_profile_summary(profile)
        return profile

    except json.JSONDecodeError as e:
        print(f"  ❌ Failed to parse GPT response as JSON: {e}")
        return {}
    except Exception as e:
        print(f"  ❌ Resume parsing failed: {e}")
        return {}


def load_profile() -> dict:
    """
    Load the cached candidate profile.
    Returns empty dict if no profile exists.
    """
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH, "r") as f:
            return json.load(f)
    return {}


def profile_exists() -> bool:
    """Check if a cached profile exists."""
    return PROFILE_PATH.exists()


def _save_profile(profile: dict):
    """Save profile to disk."""
    settings.DATA_DIR.mkdir(exist_ok=True)
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)


def _validate_profile(profile: dict) -> dict:
    """Ensure all expected keys exist with correct types."""
    defaults = {
        "name": "",
        "email": "",
        "phone": "",
        "location": "",
        "linkedin": "",
        "github": "",
        "portfolio": "",
        "visa_status": "unknown",
        "education": [],
        "years_experience": 0,
        "programming_languages": [],
        "tools_and_platforms": [],
        "ml_techniques": [],
        "domain_knowledge": [],
        "soft_skills": [],
        "certifications": [],
        "work_experience": [],
    }

    for key, default in defaults.items():
        if key not in profile:
            profile[key] = default
        elif isinstance(default, list) and not isinstance(profile[key], list):
            profile[key] = [profile[key]] if profile[key] else []

    return profile


def _print_profile_summary(profile: dict):
    """Print a summary of the parsed profile."""
    print(f"\n  {'─' * 50}")
    print(f"  👤 {profile.get('name', 'Unknown')}")
    print(f"  📍 {profile.get('location', 'Unknown')}")
    print(f"  📧 {profile.get('email', 'Unknown')}")
    print(f"  🎓 {len(profile.get('education', []))} degrees")
    print(f"  💼 {len(profile.get('work_experience', []))} work experiences")
    print(f"  📅 {profile.get('years_experience', 0)} years total experience")
    print(f"  💻 Languages: {', '.join(profile.get('programming_languages', []))}")
    print(f"  🛠️  Tools: {', '.join(profile.get('tools_and_platforms', []))}")
    print(f"  🧠 ML: {', '.join(profile.get('ml_techniques', [])[:5])}...")
    print(f"  🏛️  Visa: {profile.get('visa_status', 'unknown')}")
    print(f"  {'─' * 50}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        # Try loading existing profile
        if profile_exists():
            profile = load_profile()
            print("📦 Loaded cached profile:")
            _print_profile_summary(profile)
        else:
            print("Usage: python -m parsers.resume_parser path/to/resume.pdf")
            print("       This will parse the resume and cache the profile for matching.")
    else:
        pdf_path = sys.argv[1]
        profile = parse_resume(pdf_path)
