"""
Database initialization — creates tables in Neon PostgreSQL.

Usage:
    python -m db.init_db
"""

import psycopg2
from config import settings


SCHEMA_SQL = """
-- Jobs table: core storage for all scraped positions
CREATE TABLE IF NOT EXISTS jobs (
    id              SERIAL PRIMARY KEY,
    job_hash        VARCHAR(16) UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT NOT NULL,
    source          VARCHAR(20) NOT NULL,
    url             TEXT NOT NULL,
    description     TEXT DEFAULT '',
    salary_min      INTEGER,
    salary_max      INTEGER,
    posted_date     TIMESTAMP,
    scraped_at      TIMESTAMP DEFAULT NOW(),

    -- H1B enrichment
    h1b_filings     INTEGER DEFAULT 0,
    h1b_avg_salary  INTEGER,
    sponsors_h1b    BOOLEAN,

    -- Scoring
    h1b_score       REAL DEFAULT 0.0,

    -- Application tracking
    status          VARCHAR(20) DEFAULT 'new',
    applied_at      TIMESTAMP,
    notes           TEXT DEFAULT '',

    -- Metadata
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- H1B sponsors cache: company-level sponsorship data
CREATE TABLE IF NOT EXISTS h1b_sponsors (
    id                      SERIAL PRIMARY KEY,
    company_name            TEXT NOT NULL,
    normalized_name         TEXT UNIQUE NOT NULL,
    total_filings           INTEGER DEFAULT 0,
    data_scientist_filings  INTEGER DEFAULT 0,
    avg_salary              INTEGER DEFAULT 0,
    approval_rate           REAL DEFAULT 0.0,
    last_filing_year        INTEGER DEFAULT 0,
    updated_at              TIMESTAMP DEFAULT NOW()
);

-- Application history: tracks every application + feedback (Phase 3)
CREATE TABLE IF NOT EXISTS applications (
    id              SERIAL PRIMARY KEY,
    job_id          INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    cover_letter    TEXT,
    resume_version  TEXT,
    applied_at      TIMESTAMP DEFAULT NOW(),
    status          VARCHAR(20) DEFAULT 'applied',

    -- RLHF feedback
    user_rating     INTEGER,          -- 1-5 rating of generated cover letter
    user_edits      TEXT,             -- what the user changed
    feedback_notes  TEXT,             -- free-form feedback
    callback        BOOLEAN DEFAULT FALSE,

    updated_at      TIMESTAMP DEFAULT NOW()
);
-- Match results: stores JD parsing + resume match scores
CREATE TABLE IF NOT EXISTS match_results (
    id              SERIAL PRIMARY KEY,
    job_hash        VARCHAR(16) REFERENCES jobs(job_hash) ON DELETE CASCADE,
    match_score     REAL,
    h1b_score       REAL,
    combined_score  REAL,
    fit_tier        VARCHAR(30),
    parsed_jd       JSONB,
    strengths       JSONB,
    gaps            JSONB,
    cover_letter_angles JSONB,
    matched_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(job_hash)
);

CREATE INDEX IF NOT EXISTS idx_match_combined ON match_results (combined_score DESC);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_jobs_company     ON jobs (company);
CREATE INDEX IF NOT EXISTS idx_jobs_status      ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_h1b_score   ON jobs (h1b_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_salary_min  ON jobs (salary_min DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_jobs_scraped     ON jobs (scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_h1b_normalized   ON h1b_sponsors (normalized_name);
CREATE INDEX IF NOT EXISTS idx_applications_job ON applications (job_id);
"""


def init_database():
    """Create all tables and indexes."""
    print("🔌 Connecting to Neon PostgreSQL...")
    conn = psycopg2.connect(settings.DATABASE_URL)
    conn.autocommit = True

    with conn.cursor() as cur:
        print("📦 Creating tables...")
        cur.execute(SCHEMA_SQL)

    # Verify
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cur.fetchall()]

    conn.close()

    print(f"✅ Database initialized! Tables: {', '.join(tables)}")
    return tables


if __name__ == "__main__":
    init_database()
