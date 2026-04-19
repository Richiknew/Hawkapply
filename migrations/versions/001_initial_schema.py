"""Initial schema — jobs, h1b_sponsors, applications, match_results

Revision ID: 001
Revises:
Create Date: 2026-04-12
"""

from __future__ import annotations

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
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
            h1b_filings     INTEGER DEFAULT 0,
            h1b_avg_salary  INTEGER,
            sponsors_h1b    BOOLEAN,
            h1b_score       REAL DEFAULT 0.0,
            status          VARCHAR(20) DEFAULT 'new',
            applied_at      TIMESTAMP,
            notes           TEXT DEFAULT '',
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("""
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
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id              SERIAL PRIMARY KEY,
            job_id          INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
            cover_letter    TEXT,
            resume_version  TEXT,
            applied_at      TIMESTAMP DEFAULT NOW(),
            status          VARCHAR(20) DEFAULT 'applied',
            user_rating     INTEGER,
            user_edits      TEXT,
            feedback_notes  TEXT,
            callback        BOOLEAN DEFAULT FALSE,
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS match_results (
            id                  SERIAL PRIMARY KEY,
            job_hash            VARCHAR(16) REFERENCES jobs(job_hash) ON DELETE CASCADE,
            match_score         REAL,
            h1b_score           REAL,
            combined_score      REAL,
            fit_tier            VARCHAR(30),
            parsed_jd           JSONB,
            strengths           JSONB,
            gaps                JSONB,
            cover_letter_angles JSONB,
            matched_at          TIMESTAMP DEFAULT NOW(),
            UNIQUE(job_hash)
        )
    """)
    # Indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company    ON jobs (company)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status     ON jobs (status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_h1b_score  ON jobs (h1b_score DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_salary_min ON jobs (salary_min DESC NULLS LAST)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_scraped    ON jobs (scraped_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_h1b_normalized  ON h1b_sponsors (normalized_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_applications_job ON applications (job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_match_combined  ON match_results (combined_score DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS match_results")
    op.execute("DROP TABLE IF EXISTS applications")
    op.execute("DROP TABLE IF EXISTS h1b_sponsors")
    op.execute("DROP TABLE IF EXISTS jobs")
