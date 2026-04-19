// Client-side API functions — all calls go through Next.js proxy routes
// so the HAWKAPI_KEY never reaches the browser.

import type {
  JobListResponse,
  Job,
  JobUpdate,
  MatchResult,
  MatchRunResponse,
  MatchRunStatus,
  PipelineFilters,
  PipelineRunResponse,
  PipelineStatus,
  Stats,
  CandidateProfile,
} from "./types";

const BASE = "/api"; // relative → always same-origin

async function request<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

export function fetchJobs(params?: {
  status?: string;
  sponsor?: boolean;
  search?: string;
  source?: string;
  location?: string;
  minSalary?: number;
  limit?: number;
  offset?: number;
}): Promise<JobListResponse> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.sponsor !== undefined) qs.set("sponsor", String(params.sponsor));
  if (params?.search) qs.set("search", params.search);
  if (params?.source) qs.set("source", params.source);
  if (params?.location) qs.set("location", params.location);
  if (params?.minSalary) qs.set("min_salary", String(params.minSalary));
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  const query = qs.toString() ? `?${qs}` : "";
  return request<JobListResponse>(`/jobs${query}`);
}

export function fetchJob(jobHash: string): Promise<Job> {
  return request<Job>(`/jobs/${jobHash}`);
}

export function updateJob(jobHash: string, data: JobUpdate): Promise<Job> {
  return request<Job>(`/jobs/${jobHash}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

// ── Matches ───────────────────────────────────────────────────────────────────

export function fetchMatches(params?: {
  tier?: string;
  limit?: number;
  offset?: number;
}): Promise<MatchResult[]> {
  const qs = new URLSearchParams();
  if (params?.tier) qs.set("tier", params.tier);
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  const query = qs.toString() ? `?${qs}` : "";
  return request<MatchResult[]>(`/match/results${query}`);
}

export function runMatching(aiThreshold = 0.6, limit = 100): Promise<MatchRunResponse> {
  return request<MatchRunResponse>("/match/run", {
    method: "POST",
    body: JSON.stringify({ limit, ai_threshold: aiThreshold * 100 }),
  });
}

export function fetchMatchRunStatus(runId: string): Promise<MatchRunStatus> {
  return request<MatchRunStatus>(`/match/runs/${runId}`);
}

// ── Pipeline ──────────────────────────────────────────────────────────────────

export function fetchPipelineConfig(): Promise<PipelineFilters> {
  return request<PipelineFilters>("/pipeline/config");
}

export function updatePipelineConfig(data: {
  target_roles: string[];
  locations: string[];
  min_salary: number;
  posted_within_days: number;
  min_h1b_filings: number;
  require_sponsorship: boolean;
}): Promise<PipelineFilters> {
  return request<PipelineFilters>("/pipeline/config", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function runPipeline(): Promise<PipelineRunResponse> {
  return request<PipelineRunResponse>("/pipeline/run", { method: "POST", body: "{}" });
}

export function fetchPipelineStatus(runId: string): Promise<PipelineStatus> {
  return request<PipelineStatus>(`/pipeline/status?run_id=${encodeURIComponent(runId)}`);
}

export function fetchPipelineRuns(): Promise<PipelineStatus[]> {
  return request<PipelineStatus[]>("/pipeline/runs");
}

export function cancelPipeline(runId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/pipeline/cancel/${runId}`, { method: "POST" });
}

// ── Stats ─────────────────────────────────────────────────────────────────────

export function fetchStats(): Promise<Stats> {
  return request<Stats>("/stats");
}

// ── Resume ────────────────────────────────────────────────────────────────────

export function fetchProfile(): Promise<CandidateProfile> {
  return request<CandidateProfile>("/resume/profile");
}

export async function uploadResume(file: File): Promise<{ message: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/resume/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}
