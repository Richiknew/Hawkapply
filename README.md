# HawkApply — AI-Powered H1B Job Application Pipeline

## Phase 1: Job Scraping + H1B Filtering Engine

### What this does
1. Scrapes data science jobs from Indeed and LinkedIn (via RSS/API)
2. Cross-references companies against H1B sponsorship history (MyVisaJobs data)
3. Filters by salary floor ($130K+) and sponsorship likelihood
4. Stores deduplicated results in Neon PostgreSQL
5. Scores and ranks jobs by H1B-friendliness

### Setup

#### 1. Clone and install dependencies
```bash
cd hawkapply
pip install -r requirements.txt
```

#### 2. Set up Neon PostgreSQL (free tier)
1. Go to https://neon.tech and sign up (GitHub login works)
2. Create a new project called "hawkapply"
3. Copy your connection string from the dashboard
4. Create `.env` file:
```
DATABASE_URL=postgresql://user:pass@ep-xyz.us-east-2.aws.neon.tech/hawkapply?sslmode=require
ANTHROPIC_API_KEY=sk-ant-...  # For Phase 2 (cover letters)
```

#### 3. Initialize the database
```bash
python -m db.init_db
```

#### 4. Run the scraper
```bash
# Scrape jobs from Indeed
python -m scrapers.indeed_scraper

# Cross-reference H1B sponsorship data
python -m scrapers.h1b_matcher

# Run the full pipeline (scrape + match + score)
python main.py
```

#### 5. View results
```bash
python view_jobs.py
```

### Project Structure
```
hawkapply/
├── main.py                 # Full pipeline orchestrator
├── view_jobs.py            # CLI to view/filter scraped jobs
├── requirements.txt
├── .env.example
├── config/
│   └── settings.py         # Configuration + env loading
├── db/
│   ├── init_db.py          # Database schema creation
│   ├── models.py           # Data classes
│   └── operations.py       # CRUD operations
├── scrapers/
│   ├── indeed_scraper.py   # Indeed job scraper
│   ├── linkedin_rss.py     # LinkedIn RSS feed parser
│   └── h1b_matcher.py      # H1B sponsorship cross-reference
├── utils/
│   ├── deduplicator.py     # Job deduplication logic
│   └── scorer.py           # Job ranking/scoring engine
└── data/
    └── h1b_sponsors.json   # Cached H1B sponsor data
```

### Architecture Decisions
- **Neon PostgreSQL**: Free tier, scale-to-zero, real SQL — no SQLite file management headaches
- **No Selenium for Phase 1**: We use HTTP requests + BeautifulSoup to stay lightweight and avoid bot detection. LinkedIn via RSS/public feeds only.
- **Deduplication**: Jobs matched by (company + title + location) hash to avoid duplicates across sources
- **Scoring**: Each job gets an H1B-friendliness score (0-100) based on company sponsorship history, salary, and location
