// ── Jobs ──────────────────────────────────────────────────────────────────────

export interface Job {
  id: number;
  job_hash: string;
  title: string;
  company: string;
  location: string | null;
  source: string;
  url: string;
  description: string | null;
  salary_min: number | null;
  salary_max: number | null;
  posted_date: string | null;
  scraped_at: string;
  h1b_filings: number | null;
  h1b_avg_salary: number | null;
  sponsors_h1b: boolean;
  h1b_score: number | null;
  status: JobStatus;
  applied_at: string | null;
  notes: string | null;
  updated_at: string;
}

export type JobStatus =
  | "new"
  | "reviewing"
  | "applied"
  | "interview"
  | "rejected"
  | "offer";

export interface JobListResponse {
  total: number;
  limit: number;
  offset: number;
  items: Job[];
}

export interface JobUpdate {
  status?: JobStatus;
  notes?: string;
}

// ── Match ─────────────────────────────────────────────────────────────────────

export interface MatchResult {
  // job fields (joined)
  id: number;
  job_hash: string;
  title: string;
  company: string;
  location: string | null;
  source: string;
  url: string;
  salary_min: number | null;
  salary_max: number | null;
  status: JobStatus;
  sponsors_h1b: boolean;
  h1b_filings: number | null;
  h1b_avg_salary: number | null;
  // match fields
  match_score: number;       // 0–100
  h1b_score: number;         // 0–100
  combined_score: number;    // 0–100
  fit_tier: string;          // "Strong Match" | "Good Match" | "Stretch Match"
  strengths: string[];
  gaps: string[];
  cover_letter_angles: string[];
  matched_at: string;
  parsed_jd: unknown | null;
}

export interface MatchRunResponse {
  run_id: string;
  message: string;
  status: string;
}

export interface MatchRunStatus {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed";
  matched: number;
  total: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

// ── Pipeline ──────────────────────────────────────────────────────────────────

export interface PipelineRunResponse {
  run_id: string;
  message: string;
  status: string;
}

export interface PipelineFilters {
  target_roles: string[];
  locations: string[];
  min_salary: number;
  posted_within_days: number;
  min_h1b_filings: number;
  require_sponsorship: boolean;
  company_count: number;
}

export interface PipelineStatus {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  jobs_scraped: number;
  jobs_matched: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  message: string;
  filters: PipelineFilters | null;
}

// ── Stats ─────────────────────────────────────────────────────────────────────

export interface Stats {
  jobs: {
    total_jobs: number;
    sponsoring_jobs: number;
    high_salary_jobs: number;
    new_jobs: number;
    reviewing_jobs: number;
    applied_jobs: number;
    interview_jobs: number;
    offer_jobs: number;
    rejected_jobs: number;
    avg_h1b_score: number;
    unique_companies: number;
    last_scraped_at: string | null;
  };
  match: {
    total_matched: number;
    avg_combined_score: number;
    strong_matches: number;
    good_matches: number;
    stretch_matches: number;
  };
  by_source: Array<{ source: string; count: number }>;
  by_h1b_tier: Array<{ tier: string; count: number }>;
  config: {
    min_salary: number;
  };
}

// ── Resume ────────────────────────────────────────────────────────────────────

export interface Education {
  degree: string;
  school: string;
  location?: string;
  gpa?: number;
  graduation?: string;
}

export interface WorkExperience {
  title: string;
  company: string;
  location?: string;
  dates?: string;
  highlights?: string[];
}

export interface CandidateProfile {
  name?: string;
  email?: string;
  phone?: string;
  location?: string;
  linkedin?: string;
  github?: string;
  portfolio?: string;
  visa_status?: string;
  years_experience?: number;
  education?: Education[];
  work_experience?: WorkExperience[];
  programming_languages?: string[];
  tools_and_platforms?: string[];
  ml_techniques?: string[];
  domain_knowledge?: string[];
  soft_skills?: string[];
  certifications?: string[];
  [key: string]: unknown;
}
