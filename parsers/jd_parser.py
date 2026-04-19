"""
Job Description Parser — extracts structured requirements from raw JD text.

Uses GPT-4o-mini (cheap, fast) to extract:
  - Required skills (technical + tools)
  - Years of experience
  - Education requirements
  - Domain knowledge
  - Nice-to-haves vs hard requirements
  - Visa/sponsorship signals

Usage:
    from parsers.jd_parser import parse_jd
    result = parse_jd(job_description_text)
"""

import json
import re
from openai import OpenAI
from config import settings


client = OpenAI(api_key=settings.OPENAI_API_KEY)

PARSE_PROMPT = """You are a job description parser. Extract structured information from the following job description.

Return ONLY valid JSON with this exact schema (no markdown, no backticks):
{
    "required_skills": ["skill1", "skill2"],
    "preferred_skills": ["skill1", "skill2"],
    "programming_languages": ["Python", "SQL"],
    "tools_and_platforms": ["Databricks", "AWS", "Spark"],
    "ml_techniques": ["logistic regression", "random forest"],
    "years_experience_min": 3,
    "years_experience_max": 5,
    "education": {
        "degree": "Masters",
        "fields": ["Data Science", "Computer Science", "Statistics"]
    },
    "domain_knowledge": ["marketing", "finance", "advertising"],
    "soft_skills": ["communication", "stakeholder management"],
    "visa_sponsorship": "yes/no/unknown",
    "clearance_required": false,
    "remote_policy": "remote/hybrid/onsite/unknown",
    "seniority_level": "junior/mid/senior/unknown",
    "key_responsibilities": ["responsibility1", "responsibility2"],
    "team_or_department": "Marketing Analytics"
}

Rules:
- Only include information explicitly stated in the JD
- For years_experience, use -1 if not mentioned
- For visa_sponsorship: "yes" if they mention sponsoring, "no" if they say no sponsorship, "unknown" otherwise
- Keep skills lowercase and concise
- Separate hard requirements from nice-to-haves"""


def parse_jd_local(description: str) -> dict:
    """Quick local keyword extraction from JD text. No API call."""
    desc = (description or "").lower()

    langs = []
    for lang in ["python", "sql", "pyspark", "r ", "pytorch", "sas"]:
        if lang in desc:
            langs.append(lang.strip())

    tools = []
    for tool in [
        "databricks", "aws", "gcp", "azure", "spark", "hadoop", "airflow",
        "dbt", "tableau", "power bi", "snowflake", "redshift", "bigquery",
        "sagemaker", "mlflow", "docker", "kubernetes", "git", "jenkins",
        "kafka", "s3", "ec2", "emr", "glue", "looker",
    ]:
        if tool in desc:
            tools.append(tool)

    ml = []
    for technique in [
        "logistic regression", "random forest", "xgboost", "deep learning",
        "neural network", "nlp", "computer vision", "a/b test", "hypothesis test",
        "clustering", "classification", "regression", "time series",
        "recommendation", "reinforcement learning", "transformer",
        "lstm", "cnn", "bert", "llm", "generative ai", "causal inference",
        "bayesian", "gradient boost", "feature engineering",
    ]:
        if technique in desc:
            ml.append(technique)

    domains = []
    for domain in [
        "marketing", "advertising", "finance", "banking", "insurance",
        "healthcare", "retail", "e-commerce", "supply chain", "logistics",
        "media", "ad tech", "risk", "fraud", "pricing", "forecasting",
    ]:
        if domain in desc:
            domains.append(domain)

    yrs_match = re.search(r"(\d+)\+?\s*(?:years|yrs)", desc)
    yrs = int(yrs_match.group(1)) if yrs_match else -1

    return {
        "programming_languages": langs,
        "tools_and_platforms": tools,
        "ml_techniques": ml,
        "domain_knowledge": domains,
        "years_experience_min": yrs,
        "education": {
            "degree": "masters" if "master" in desc else "bachelors" if "bachelor" in desc else "",
            "fields": [],
        },
        "required_skills": langs + tools + ml,
        "preferred_skills": [],
    }


def parse_jd(description: str, title: str = "", company: str = "") -> dict:
    """
    Parse a job description into structured requirements.
    
    Args:
        description: Raw job description text
        title: Job title (for context)
        company: Company name (for context)
    
    Returns:
        Dict with structured requirements
    """
    if not description or not settings.OPENAI_API_KEY:
        return _empty_result()

    context = ""
    if title:
        context += f"Job Title: {title}\n"
    if company:
        context += f"Company: {company}\n"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PARSE_PROMPT},
                {"role": "user", "content": f"{context}\nJob Description:\n{description[:4000]}"},
            ],
            temperature=0.1,
            max_tokens=1000,
        )

        raw = response.choices[0].message.content.strip()
        # Clean any markdown wrapping
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        result = json.loads(raw)
        return _validate_result(result)

    except json.JSONDecodeError as e:
        print(f"  ⚠️  JD parse JSON error: {e}")
        return _empty_result()
    except Exception as e:
        print(f"  ⚠️  JD parse failed: {e}")
        if "429" in str(e) or "insufficient_quota" in str(e):
            raise  # Let it bubble up to stop the batch
        return _empty_result()


def parse_jd_batch(jobs: list[dict], limit: int = 50) -> dict[str, dict]:
    """
    Parse multiple job descriptions. Returns {job_hash: parsed_result}.
    Limits API calls to stay within budget.
    """
    results = {}
    for i, job in enumerate(jobs[:limit]):
        job_hash = job.get("job_hash", str(i))
        desc = job.get("description", "")
        title = job.get("title", "")
        company = job.get("company", "")

        if not desc:
            results[job_hash] = _empty_result()
            continue

        print(f"  📝 Parsing [{i+1}/{min(len(jobs), limit)}] {title} @ {company}...")
        results[job_hash] = parse_jd(desc, title, company)

    return results


def _empty_result() -> dict:
    return {
        "required_skills": [],
        "preferred_skills": [],
        "programming_languages": [],
        "tools_and_platforms": [],
        "ml_techniques": [],
        "years_experience_min": -1,
        "years_experience_max": -1,
        "education": {"degree": "unknown", "fields": []},
        "domain_knowledge": [],
        "soft_skills": [],
        "visa_sponsorship": "unknown",
        "clearance_required": False,
        "remote_policy": "unknown",
        "seniority_level": "unknown",
        "key_responsibilities": [],
        "team_or_department": "unknown",
    }


def _validate_result(result: dict) -> dict:
    """Ensure all expected keys exist with correct types."""
    template = _empty_result()
    for key, default in template.items():
        if key not in result:
            result[key] = default
        elif isinstance(default, list) and not isinstance(result[key], list):
            result[key] = [result[key]] if result[key] else []
        elif isinstance(default, dict) and not isinstance(result[key], dict):
            result[key] = default
    return result


if __name__ == "__main__":
    # Quick test
    sample_jd = """
    We are looking for a Data Scientist to join our Marketing Analytics team.
    
    Requirements:
    - 3+ years of experience in data science or machine learning
    - Strong proficiency in Python, SQL, and PySpark
    - Experience with A/B testing and statistical analysis
    - Masters degree in Data Science, Statistics, or related field
    - Experience with cloud platforms (AWS, Databricks)
    - Knowledge of marketing attribution and media mix modeling
    
    Nice to have:
    - Experience with deep learning frameworks (PyTorch, TensorFlow)
    - Knowledge of causal inference methods
    - Experience in ad tech or media industry
    
    We offer visa sponsorship for qualified candidates.
    """

    result = parse_jd(sample_jd, "Data Scientist", "Optimum Media")
    print(json.dumps(result, indent=2))
