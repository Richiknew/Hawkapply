# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

HawkApply is an AI-powered job application pipeline for H1B visa candidates. It:
1. Scrapes data science jobs from free APIs (JSearch/RapidAPI, Adzuna, LinkedIn RSS, RemoteOK) and direct company career pages
2. Cross-references companies against H1B sponsorship history and scores each job 0–100
3. Parses job descriptions (GPT-4o-mini) and matches them against a candidate's parsed resume
4. Generates application autofill data for common ATS platforms (Greenhouse, Lever, Workday, Ashby)

The target user is Shreya Sahay — a Data Scientist on OPT STEM Extension who needs H1B sponsorship.

## Setup

```bash
pip install -r requirements.txt
```

Create `.env` in the project root:
```
DATABASE_URL=postgresql://user:pass@ep-xyz.us-east-2.aws.neon.tech/hawkapply?sslmode=require
OPENAI_API_KEY=sk-...
RAPIDAPI_KEY=...       # Optional: JSearch API
ADZUNA_APP_ID=...      # Optional: Adzuna API
ADZUNA_APP_KEY=...
API_KEY=...            # Optional: FastAPI auth key
DASHBOARD_URL=...      # Optional: allowed CORS origin
```

## Key Commands

```bash
# Initialize database tables (run once)
python -m db.init_db

# Full pipeline: scrape → store → H1B match → score
python main.py
python main.py --refresh-h1b    # Force refresh H1B sponsor data from MyVisaJobs

# Parse JDs and match against resume (run after main.py)
python match_jobs.py            # Fast rule-based matching
python match_jobs.py --ai       # AI matching for top candidates (uses OpenAI)
python match_jobs.py --top 20 --min-score 60 --export

# Parse resume PDF into candidate_profile.json
python -m parsers.resume_parser Resume/Shreya_Resume_tu.pdf

# View and filter jobs
python view_jobs.py
python view_jobs.py --stats

# Generate application autofill for a specific job
python autofill.py --job-hash <hash>
python autofill.py --pick           # Interactive job selector
python autofill.py --export

# Run the FastAPI server
uvicorn api.main:app --reload --port 8000
```

## Architecture

### Data Flow

```
scrapers/job_scraper.py      # Orchestrates all scraping sources
  ├── indeed_scraper.py      # Salary parsing + sponsorship signal detection
  ├── career_scraper.py      # Direct company career page scraping
  └── (JSearch, Adzuna, LinkedIn RSS, RemoteOK via job_scraper.py)
        ↓
db/operations.py             # upsert_jobs_batch() — deduplication by job_hash
        ↓
scrapers/h1b_matcher.py      # Enriches jobs with H1B sponsorship data
  └── SEED_SPONSORS[]        # 200+ known H1B sponsors with filing counts
  └── data/h1b_sponsors.json # 7-day cache of sponsor data
        ↓
utils/scorer.py              # compute_h1b_score() — 0–100 score
        ↓
match_jobs.py                # JD parsing + resume matching
  ├── parsers/jd_parser.py   # GPT-4o-mini structured extraction
  └── parsers/resume_matcher.py  # Fast rule-based + optional AI matching
        ↓
autofill.py                  # ATS-specific field formatting + GPT answer generation
```

### Database Schema (Neon PostgreSQL)

Four tables defined in `db/init_db.py`:
- `jobs` — scraped postings with H1B enrichment and `status` field (`new` → `reviewing` → `applied`)
- `h1b_sponsors` — cached sponsorship data keyed on `normalized_name`
- `match_results` — JD parse results + resume match scores, linked to `jobs.job_hash`
- `applications` — application history with RLHF feedback fields (Phase 3, not yet wired up)

Deduplication: `job_hash = SHA256(company|title|location)[:16]`. Each pipeline run deletes all `status='new'` jobs before re-inserting fresh results.

### Scoring Logic (`utils/scorer.py`)

`compute_h1b_score()` — 40 pts filing history + 30 pts salary + 20 pts sponsorship signals + 10 pts recency.

`match_resume_fast()` — rule-based: 20 pts languages + 20 pts tools + 20 pts ML techniques + 15 pts experience + 10 pts education + 15 pts domain.

Combined score in `match_jobs.py`: `match_score × 0.6 + h1b_score × 0.4`.

### FastAPI Server (`api/`)

Routers: `/jobs`, `/pipeline`, `/match`, `/resume`, `/stats`, `/health`. Uses a psycopg2 connection pool managed in `api/dependencies.py`. API key auth via `settings.API_KEY`. Logs to `logs/api.log`.

### Candidate Profile

Parsed from PDF by `parsers/resume_parser.py` → saved to `data/candidate_profile.json`. Used by `resume_matcher.py` and `autofill.py`. Run the parser whenever the resume changes.

## Configuration (`config/__init__.py`)

All config flows through the `settings` singleton. Key tunables:
- `TARGET_ROLES` — comma-separated, defaults to `"data scientist"`
- `LOCATIONS` — defaults to 30+ US cities + Remote
- `MIN_SALARY` — defaults to 130000
- `MIN_H1B_FILINGS` — defaults to 5
- `MAX_PAGES_PER_SEARCH` — defaults to 5
- `REQUEST_DELAY` — defaults to 2.0s (respect rate limits)

## GitHub Actions

`.github/workflows/daily_scrape.yml` runs `python main.py` Mon–Fri at 8 AM EST using secrets `DATABASE_URL` and `ANTHROPIC_API_KEY`. Requires those secrets set in repo Settings → Secrets → Actions.

## Notes

- All DB queries use raw psycopg2 (not an ORM). SQLAlchemy is a dependency only for Alembic migrations.
- The `scrapers/indeed_scraper.py` is the old scraper; the active one called by `main.py` is `scrapers/job_scraper.py` via `run_all_scrapers()`.
- `SHREYA_PROFILE` in `resume_matcher.py` is commented out; the live code calls `get_profile()` which reads `data/candidate_profile.json`.
- AI features (`jd_parser`, `match_resume_ai`, `autofill` custom answers) use `gpt-4o-mini` and require `OPENAI_API_KEY`.
