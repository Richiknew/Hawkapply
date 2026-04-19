"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchJobs, fetchPipelineConfig, updateJob } from "@/lib/api";
import type { JobStatus } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ExternalLink, Search, X, Info } from "lucide-react";
import { toast } from "sonner";

const STATUSES: JobStatus[] = [
  "new",
  "reviewing",
  "applied",
  "interview",
  "rejected",
  "offer",
];

const STATUS_COLORS: Record<JobStatus, string> = {
  new: "bg-blue-100 text-blue-800",
  reviewing: "bg-yellow-100 text-yellow-800",
  applied: "bg-purple-100 text-purple-800",
  interview: "bg-orange-100 text-orange-800",
  rejected: "bg-red-100 text-red-800",
  offer: "bg-green-100 text-green-800",
};

const SOURCES = [
  { value: "career_page", label: "Company Career Pages" },
  { value: "jsearch", label: "JSearch" },
  { value: "adzuna", label: "Adzuna" },
  { value: "linkedin_rss", label: "LinkedIn RSS" },
  { value: "remoteok", label: "Remote OK" },
  { value: "extension", label: "Browser Extension" },
];

const SALARY_OPTIONS = [
  { value: "100000", label: "$100k+" },
  { value: "130000", label: "$130k+" },
  { value: "150000", label: "$150k+" },
  { value: "180000", label: "$180k+" },
  { value: "200000", label: "$200k+" },
];

const ATS_SOURCES = ["Greenhouse", "Lever", "Ashby", "SmartRecruiters", "Workday"];

function formatPostedWindow(days: number) {
  if (days <= 1) return "Today";
  return `Last ${days} days`;
}

function formatLocations(locations: string[]) {
  if (!locations.length) return "No locations configured";
  const hasRemote = locations.some((location) => location.toLowerCase() === "remote");
  const cityCount = locations.filter((location) => location.toLowerCase() !== "remote").length;
  return `${cityCount} ${cityCount === 1 ? "city" : "cities"}${hasRemote ? " + Remote" : ""}`;
}

const PAGE_SIZE = 50;

export default function JobsPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sponsorFilter, setSponsorFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [locationFilter, setLocationFilter] = useState<string>("");
  const [minSalaryFilter, setMinSalaryFilter] = useState<string>("all");
  const [page, setPage] = useState(0);
  const [showConfig, setShowConfig] = useState(false);

  const qc = useQueryClient();

  const { data: pipelineConfig, isLoading: isConfigLoading } = useQuery({
    queryKey: ["pipeline-config"],
    queryFn: fetchPipelineConfig,
    staleTime: 60_000,
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ["jobs", search, statusFilter, sponsorFilter, sourceFilter, locationFilter, minSalaryFilter, page],
    queryFn: () =>
      fetchJobs({
        search: search || undefined,
        status: statusFilter !== "all" ? statusFilter : undefined,
        sponsor: sponsorFilter === "yes" ? true : sponsorFilter === "no" ? false : undefined,
        source: sourceFilter !== "all" ? sourceFilter : undefined,
        location: locationFilter || undefined,
        minSalary: minSalaryFilter !== "all" ? parseInt(minSalaryFilter) : undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  const patchMutation = useMutation({
    mutationFn: ({ jobHash, status }: { jobHash: string; status: JobStatus }) =>
      updateJob(jobHash, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Status updated");
    },
    onError: () => toast.error("Failed to update status"),
  });

  const total = data?.total ?? 0;
  const jobs = data?.items ?? [];
  const totalPages = Math.ceil(total / PAGE_SIZE);

  // Build active filter chips
  const activeFilters: { label: string; clear: () => void }[] = [];
  if (statusFilter !== "all") activeFilters.push({ label: `Status: ${statusFilter}`, clear: () => { setStatusFilter("all"); setPage(0); } });
  if (sponsorFilter !== "all") activeFilters.push({ label: `H1B: ${sponsorFilter === "yes" ? "Sponsors only" : "Non-sponsors"}`, clear: () => { setSponsorFilter("all"); setPage(0); } });
  if (sourceFilter !== "all") {
    const src = SOURCES.find((s) => s.value === sourceFilter)?.label ?? sourceFilter;
    activeFilters.push({ label: `Source: ${src}`, clear: () => { setSourceFilter("all"); setPage(0); } });
  }
  if (locationFilter) activeFilters.push({ label: `Location: ${locationFilter}`, clear: () => { setLocationFilter(""); setPage(0); } });
  if (minSalaryFilter !== "all") {
    const sal = SALARY_OPTIONS.find((s) => s.value === minSalaryFilter)?.label ?? minSalaryFilter;
    activeFilters.push({ label: `Min salary: ${sal}`, clear: () => { setMinSalaryFilter("all"); setPage(0); } });
  }
  if (search) activeFilters.push({ label: `Search: "${search}"`, clear: () => { setSearch(""); setPage(0); } });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Jobs</h1>
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowConfig((v) => !v)}
            className="text-muted-foreground gap-1"
          >
            <Info className="h-4 w-4" />
            Scraping config
          </Button>
          <span className="text-sm text-muted-foreground">{total} total</span>
        </div>
      </div>

      {/* Scraping config info card */}
      {showConfig && (
        <div className="rounded-lg border bg-muted/40 p-4 text-sm space-y-2">
          <p className="font-semibold text-foreground">Active saved pipeline configuration</p>
          {isConfigLoading && (
            <p className="text-muted-foreground">Loading config…</p>
          )}
          {pipelineConfig && (
            <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-muted-foreground">
              <span><span className="text-foreground font-medium">Target roles:</span> {pipelineConfig.target_roles.join(", ")}</span>
              <span><span className="text-foreground font-medium">Min salary:</span> ${(pipelineConfig.min_salary / 1000).toFixed(0)}k</span>
              <span><span className="text-foreground font-medium">Posted within:</span> {formatPostedWindow(pipelineConfig.posted_within_days)}</span>
              <span><span className="text-foreground font-medium">Locations:</span> {formatLocations(pipelineConfig.locations)}</span>
              <span><span className="text-foreground font-medium">H1B sponsor companies:</span> {pipelineConfig.company_count}</span>
              <span><span className="text-foreground font-medium">Min H1B filings:</span> {pipelineConfig.min_h1b_filings}</span>
              <span><span className="text-foreground font-medium">Require sponsorship:</span> {pipelineConfig.require_sponsorship ? "Yes" : "No"}</span>
              <span><span className="text-foreground font-medium">ATS sources:</span> {ATS_SOURCES.join(", ")}</span>
              <span className="col-span-2">
                <span className="text-foreground font-medium">Filters applied:</span>{" "}
                US jobs only · posted-date window · DS/ML keyword match
                {pipelineConfig.require_sponsorship ? " · H1B sponsor cross-reference" : ""}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search title or company…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            className="pl-8"
          />
        </div>

        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v ?? "all"); setPage(0); }}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={sponsorFilter} onValueChange={(v) => { setSponsorFilter(v ?? "all"); setPage(0); }}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="H1B" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All H1B</SelectItem>
            <SelectItem value="yes">Sponsors</SelectItem>
            <SelectItem value="no">Non-sponsors</SelectItem>
          </SelectContent>
        </Select>

        <Select value={sourceFilter} onValueChange={(v) => { setSourceFilter(v ?? "all"); setPage(0); }}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All sources</SelectItem>
            {SOURCES.map((s) => (
              <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          placeholder="Location…"
          value={locationFilter}
          onChange={(e) => { setLocationFilter(e.target.value); setPage(0); }}
          className="w-36"
        />

        <Select value={minSalaryFilter} onValueChange={(v) => { setMinSalaryFilter(v ?? "all"); setPage(0); }}>
          <SelectTrigger className="w-32">
            <SelectValue placeholder="Min salary" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any salary</SelectItem>
            {SALARY_OPTIONS.map((s) => (
              <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Active filter chips */}
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-muted-foreground">Active filters:</span>
          {activeFilters.map((f) => (
            <Badge
              key={f.label}
              variant="secondary"
              className="gap-1 cursor-pointer pr-1 text-xs"
              onClick={f.clear}
            >
              {f.label}
              <X className="h-3 w-3" />
            </Badge>
          ))}
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs text-muted-foreground"
            onClick={() => {
              setSearch(""); setStatusFilter("all"); setSponsorFilter("all");
              setSourceFilter("all"); setLocationFilter(""); setMinSalaryFilter("all");
              setPage(0);
            }}
          >
            Clear all
          </Button>
        </div>
      )}

      {/* Table */}
      {isError && (
        <p className="text-destructive text-sm">Failed to load jobs. Is the API running?</p>
      )}

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Location</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>H1B</TableHead>
              <TableHead>Salary</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 8 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 8 }).map((__, j) => (
                      <TableCell key={j}>
                        <div className="h-4 w-full animate-pulse rounded bg-muted" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              : jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="max-w-64 truncate font-medium">
                      {job.title}
                    </TableCell>
                    <TableCell className="max-w-40 truncate">{job.company}</TableCell>
                    <TableCell className="max-w-32 truncate text-muted-foreground text-sm">
                      {job.location ?? "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {job.source}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {job.sponsors_h1b ? (
                        <Badge className="bg-emerald-100 text-emerald-800 text-xs">
                          {job.h1b_score != null ? `${job.h1b_score.toFixed(0)}%` : "Yes"}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">
                      {job.salary_min != null
                        ? `$${(job.salary_min / 1000).toFixed(0)}k`
                        : "—"}
                      {job.salary_max != null
                        ? `–$${(job.salary_max / 1000).toFixed(0)}k`
                        : ""}
                    </TableCell>
                    <TableCell>
                      <Select
                        value={job.status}
                        onValueChange={(v) =>
                          patchMutation.mutate({ jobHash: job.job_hash, status: v as JobStatus })
                        }
                      >
                        <SelectTrigger className={`h-7 w-28 text-xs ${STATUS_COLORS[job.status]}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {STATUSES.map((s) => (
                            <SelectItem key={s} value={s} className="text-xs">
                              {s.charAt(0).toUpperCase() + s.slice(1)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <a href={job.url} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                      </a>
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Page {page + 1} of {totalPages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
