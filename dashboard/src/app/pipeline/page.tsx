"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  fetchPipelineRuns,
  fetchPipelineConfig,
  updatePipelineConfig,
  runPipeline,
  fetchPipelineStatus,
  cancelPipeline,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Play,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  Square,
  Layers,
  Cpu,
  Settings2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { toast } from "sonner";
import type { PipelineFilters, PipelineStatus } from "@/lib/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatElapsed(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function parseListInput(value: string) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

const POSTED_WINDOW_OPTIONS = [
  { value: "1", label: "Today" },
  { value: "2", label: "Last 2 days" },
  { value: "3", label: "Last 3 days" },
  { value: "4", label: "Last 4 days" },
  { value: "5", label: "Last 5 days" },
  { value: "6", label: "Last 6 days" },
  { value: "7", label: "Last 7 days" },
] as const;

function formatPostedWindow(days: number) {
  return POSTED_WINDOW_OPTIONS.find((option) => Number(option.value) === days)?.label ?? "Last 7 days";
}

// ── Filters summary panel ─────────────────────────────────────────────────────

function FiltersPanel({ filters, compact = false }: { filters: PipelineFilters; compact?: boolean }) {
  return (
    <div className={`grid gap-x-6 gap-y-1 text-xs text-muted-foreground ${compact ? "grid-cols-2" : "grid-cols-1 sm:grid-cols-2"}`}>
      <div>
        <span className="font-medium text-foreground">Target roles: </span>
        {filters.target_roles.join(", ")}
      </div>
      <div>
        <span className="font-medium text-foreground">Min salary: </span>
        ${(filters.min_salary / 1000).toFixed(0)}k
      </div>
      <div>
        <span className="font-medium text-foreground">Posted within: </span>
        {formatPostedWindow(filters.posted_within_days)}
      </div>
      <div>
        <span className="font-medium text-foreground">H1B sponsor companies: </span>
        {filters.company_count}
      </div>
      <div>
        <span className="font-medium text-foreground">Min H1B filings: </span>
        {filters.min_h1b_filings}
      </div>
      <div>
        <span className="font-medium text-foreground">Require sponsorship: </span>
        {filters.require_sponsorship ? "Yes" : "No"}
      </div>
      <div>
        <span className="font-medium text-foreground">Locations: </span>
        {compact ? `${filters.locations.length} cities + Remote` : filters.locations.slice(0, 8).join(", ") + (filters.locations.length > 8 ? ` +${filters.locations.length - 8} more` : "")}
      </div>
    </div>
  );
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function ProgressBar({
  pct,
  indeterminate,
  color = "bg-primary",
}: {
  pct: number;
  indeterminate?: boolean;
  color?: string;
}) {
  return (
    <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
      {indeterminate ? (
        <div
          className={`h-full ${color} rounded-full animate-[indeterminate_1.4s_ease-in-out_infinite]`}
          style={{ width: "40%" }}
        />
      ) : (
        <div
          className={`h-full ${color} rounded-full transition-all duration-500`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      )}
    </div>
  );
}

// ── Phase row ─────────────────────────────────────────────────────────────────

type PhaseStatus = "waiting" | "active" | "done" | "error" | "cancelled";

interface Phase {
  label: string;
  description: string;
  icon: React.ReactNode;
  count: number;
  unit: string;
  status: PhaseStatus;
}

function PhaseRow({ phase }: { phase: Phase }) {
  const iconMap: Record<PhaseStatus, React.ReactNode> = {
    done:      <CheckCircle className="h-4 w-4 text-green-500" />,
    active:    <RefreshCw className="h-4 w-4 animate-spin text-blue-500" />,
    error:     <XCircle className="h-4 w-4 text-destructive" />,
    cancelled: <Square className="h-4 w-4 text-orange-400" />,
    waiting:   <Clock className="h-4 w-4 text-muted-foreground" />,
  };

  const barColor: Record<PhaseStatus, string> = {
    done:      "bg-green-500",
    active:    "bg-blue-500",
    error:     "bg-destructive",
    cancelled: "bg-orange-400",
    waiting:   "bg-muted-foreground",
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border bg-card">
          {phase.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <div>
              <p className={`text-sm font-medium leading-none ${phase.status === "waiting" ? "text-muted-foreground" : ""}`}>
                {phase.label}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">{phase.description}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {iconMap[phase.status]}
              <span className="text-sm font-semibold tabular-nums w-8 text-right">
                {phase.count > 0
                  ? phase.count
                  : phase.status === "waiting"
                  ? "—"
                  : "0"}
              </span>
            </div>
          </div>
        </div>
      </div>
      <ProgressBar
        pct={phase.status === "done" || phase.status === "cancelled" ? 100 : 0}
        indeterminate={phase.status === "active"}
        color={barColor[phase.status]}
      />
    </div>
  );
}

// ── Active run card ───────────────────────────────────────────────────────────

function ActiveRunCard({
  status,
  onCancel,
  cancelling,
}: {
  status: PipelineStatus;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const isRunning   = status.status === "running";
  const isDone      = status.status === "completed";
  const isFailed    = status.status === "failed";
  const isCancelled = status.status === "cancelled";
  const message = (status.message || "").toLowerCase();

  const elapsed = status.started_at
    ? Math.floor((Date.now() - new Date(status.started_at).getTime()) / 1000)
    : null;

  const matchingStarted =
    isDone ||
    status.jobs_matched > 0 ||
    message.includes("matching resume") ||
    message.includes("refreshing h1b sponsor dataset");
  const scrapingDone = isDone || isFailed || isCancelled || matchingStarted;
  const matchingActive = isRunning && matchingStarted && status.jobs_matched === 0;

  const phases: Phase[] = [
    {
      label: "Scraping jobs",
      description: "Fetching listings from company career pages + job boards",
      icon: <Layers className="h-4 w-4 text-blue-500" />,
      count: status.jobs_scraped,
      unit: "jobs",
      status:
        isFailed && status.jobs_scraped === 0
          ? "error"
          : isCancelled && status.jobs_scraped === 0
          ? "cancelled"
          : scrapingDone
          ? "done"
          : isRunning
          ? "active"
          : "waiting",
    },
    {
      label: "Matching resume",
      description: "Scoring jobs against your resume & H1B sponsor database",
      icon: <Cpu className="h-4 w-4 text-purple-500" />,
      count: status.jobs_matched,
      unit: "matched",
      status:
        isFailed && status.jobs_scraped > 0
          ? "error"
          : isCancelled
          ? "cancelled"
          : isDone
          ? "done"
          : matchingActive
          ? "active"
          : "waiting",
    },
  ];

  const cardClass =
    isDone
      ? "border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950/30"
      : isFailed
      ? "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/30"
      : isCancelled
      ? "border-orange-200 bg-orange-50 dark:border-orange-900 dark:bg-orange-950/30"
      : "border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950/30";

  const headerIcon =
    isDone      ? <CheckCircle className="h-5 w-5 text-green-500" /> :
    isFailed    ? <XCircle className="h-5 w-5 text-red-500" /> :
    isCancelled ? <Square className="h-5 w-5 text-orange-400" /> :
                  <RefreshCw className="h-5 w-5 animate-spin text-blue-500" />;

  const headerText =
    isDone      ? `Done — ${status.jobs_scraped} scraped, ${status.jobs_matched} matched` :
    isFailed    ? "Pipeline failed" :
    isCancelled ? "Pipeline cancelled" :
                  "Pipeline running…";

  return (
    <Card className={cardClass}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            {headerIcon}
            {headerText}
          </CardTitle>
          {isRunning && (
            <Button
              variant="outline"
              size="sm"
              onClick={onCancel}
              disabled={cancelling}
              className="h-8 gap-1.5 border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700 dark:border-red-800 dark:text-red-400"
            >
              {cancelling ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Square className="h-3.5 w-3.5" />
              )}
              {cancelling ? "Stopping…" : "Cancel"}
            </Button>
          )}
        </div>

        {/* Elapsed / timing */}
        {status.started_at && (
          <div className="flex gap-4 text-xs text-muted-foreground mt-1">
            <span>Started {new Date(status.started_at).toLocaleTimeString()}</span>
            {isRunning && elapsed !== null && (
              <span className="font-medium text-foreground">{formatElapsed(elapsed)} elapsed</span>
            )}
            {status.finished_at && (
              <span>
                Finished in{" "}
                {formatElapsed(
                  Math.floor(
                    (new Date(status.finished_at).getTime() -
                      new Date(status.started_at).getTime()) /
                      1000
                  )
                )}
              </span>
            )}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Filters used in this run */}
        {status.filters && (
          <div className="rounded-md border bg-background/70 px-3 py-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground mb-1.5">
              Filters applied in this run
            </p>
            <FiltersPanel filters={status.filters} />
          </div>
        )}

        {status.message && (
          <div className="rounded-md border bg-background/70 px-3 py-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Current step
            </p>
            <p className="mt-1 text-sm">{status.message}</p>
          </div>
        )}

        {phases.map((phase, i) => (
          <PhaseRow key={i} phase={phase} />
        ))}

        {status.error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2">
            <p className="text-xs text-destructive font-medium">Error</p>
            <p className="text-xs text-destructive/80 mt-0.5">{status.error}</p>
          </div>
        )}

        {isCancelled && status.message && (
          <p className="text-xs text-orange-600 dark:text-orange-400">{status.message}</p>
        )}
      </CardContent>
    </Card>
  );
}

// ── Status badge ───────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline"; className?: string }> = {
    completed: { label: "Done",      variant: "default",     className: "bg-green-500 hover:bg-green-600" },
    running:   { label: "Running",   variant: "secondary",   className: "text-blue-600" },
    failed:    { label: "Failed",    variant: "destructive" },
    cancelled: { label: "Cancelled", variant: "outline",     className: "border-orange-300 text-orange-600" },
    pending:   { label: "Queued",    variant: "secondary" },
  };
  const cfg = map[status] ?? { label: status, variant: "secondary" as const };
  return (
    <Badge variant={cfg.variant} className={`text-xs ${cfg.className ?? ""}`}>
      {cfg.label}
    </Badge>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "running")   return <RefreshCw className="h-4 w-4 animate-spin text-blue-500" />;
  if (status === "completed") return <CheckCircle className="h-4 w-4 text-green-500" />;
  if (status === "failed")    return <XCircle className="h-4 w-4 text-red-500" />;
  if (status === "cancelled") return <Square className="h-4 w-4 text-orange-400" />;
  return <Clock className="h-4 w-4 text-muted-foreground" />;
}

// ── Run history row ───────────────────────────────────────────────────────────

function RunHistoryRow({ run }: { run: PipelineStatus }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className="overflow-hidden">
      <CardContent className="py-3 px-4">
        <div className="flex items-center gap-3">
          <StatusIcon status={run.status} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <code className="text-xs text-muted-foreground font-mono">
                {run.run_id}
              </code>
              <StatusBadge status={run.status} />
            </div>
            <div className="flex flex-wrap gap-3 mt-1 text-xs text-muted-foreground">
              <span>
                {run.started_at
                  ? new Date(run.started_at).toLocaleString()
                  : "Queued"}
              </span>
              <span>
                Scraped:{" "}
                <strong className="text-foreground">{run.jobs_scraped}</strong>
              </span>
              <span>
                Matched:{" "}
                <strong className="text-foreground">{run.jobs_matched}</strong>
              </span>
              {run.filters && (
                <span>
                  Companies:{" "}
                  <strong className="text-foreground">{run.filters.company_count}</strong>
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {run.finished_at && run.started_at && (
              <span className="text-xs text-muted-foreground tabular-nums">
                {formatElapsed(
                  Math.floor(
                    (new Date(run.finished_at).getTime() -
                      new Date(run.started_at).getTime()) /
                      1000
                  )
                )}
              </span>
            )}
            {run.filters && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 w-7 p-0 text-muted-foreground"
                onClick={() => setExpanded((v) => !v)}
                title="Show filters"
              >
                {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </Button>
            )}
          </div>
        </div>

        {/* Expanded filters */}
        {expanded && run.filters && (
          <div className="mt-3 rounded-md border bg-muted/30 px-3 py-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground mb-1.5">
              Filters used
            </p>
            <FiltersPanel filters={run.filters} compact />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function PipelinePage() {
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [targetRolesText, setTargetRolesText] = useState("");
  const [locationsText, setLocationsText] = useState("");
  const [minSalary, setMinSalary] = useState("");
  const [postedWithinDays, setPostedWithinDays] = useState("7");
  const [minH1bFilings, setMinH1bFilings] = useState("");
  const [requireSponsorship, setRequireSponsorship] = useState(true);

  const { data: config, refetch: refetchConfig } = useQuery({
    queryKey: ["pipeline-config"],
    queryFn: fetchPipelineConfig,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!config) return;
    setTargetRolesText(config.target_roles.join("\n"));
    setLocationsText(config.locations.join("\n"));
    setMinSalary(String(config.min_salary));
    setPostedWithinDays(String(config.posted_within_days || 7));
    setMinH1bFilings(String(config.min_h1b_filings));
    setRequireSponsorship(config.require_sponsorship);
  }, [config]);

  const { data: runs, refetch: refetchRuns } = useQuery({
    queryKey: ["pipeline-runs"],
    queryFn: fetchPipelineRuns,
    refetchInterval: 3000,
    select: (data) => {
      const running = data?.find((r) => r.status === "running");
      if (running && !activeRunId) {
        setTimeout(() => setActiveRunId(running.run_id), 0);
      }
      return data;
    },
  });

  const {
    data: activeStatus,
    error: activeStatusError,
  } = useQuery({
    queryKey: ["pipeline-status", activeRunId],
    queryFn: () => fetchPipelineStatus(activeRunId!),
    enabled: !!activeRunId,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2000 : false,
  });

  useEffect(() => {
    if (!activeRunId || !activeStatusError) return;
    setActiveRunId(null);
    refetchRuns();
    toast.info("Cleared stale pipeline state");
  }, [activeRunId, activeStatusError, refetchRuns]);

  if (
    activeStatus &&
    activeStatus.status !== "running" &&
    activeRunId
  ) {
    setTimeout(() => {
      refetchRuns();
      setActiveRunId(null);
    }, 3000);
  }

  const runMutation = useMutation({
    mutationFn: runPipeline,
    onSuccess: (data) => {
      setActiveRunId(data.run_id);
      toast.info("Pipeline started!");
    },
    onError: () => toast.error("Failed to start pipeline"),
  });

  const cancelMutation = useMutation({
    mutationFn: (runId: string) => cancelPipeline(runId),
    onSuccess: () => toast.warning("Cancellation requested — stopping at next checkpoint…"),
    onError: (error) => {
      const message = error instanceof Error ? error.message : "";
      if (message.includes("Run not found")) {
        setActiveRunId(null);
        refetchRuns();
        toast.info("That run no longer exists; cleared stale state");
        return;
      }
      toast.error("Failed to request cancellation");
    },
  });

  const saveConfigMutation = useMutation({
    mutationFn: () =>
      updatePipelineConfig({
        target_roles: parseListInput(targetRolesText),
        locations: parseListInput(locationsText),
        min_salary: Number(minSalary || 0),
        posted_within_days: Number(postedWithinDays || 7),
        min_h1b_filings: Number(minH1bFilings || 0),
        require_sponsorship: requireSponsorship,
      }),
    onSuccess: async (updated) => {
      setTargetRolesText(updated.target_roles.join("\n"));
      setLocationsText(updated.locations.join("\n"));
      setMinSalary(String(updated.min_salary));
      setPostedWithinDays(String(updated.posted_within_days || 7));
      setMinH1bFilings(String(updated.min_h1b_filings));
      setRequireSponsorship(updated.require_sponsorship);
      await refetchConfig();
      toast.success("Pipeline config saved. It will apply on the next run.");
    },
    onError: () => toast.error("Failed to save pipeline config"),
  });

  const isRunning = activeStatus?.status === "running";

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Pipeline</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Scrape job listings and match them against your resume
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowConfig((v) => !v)}
            className="gap-1.5 text-muted-foreground"
          >
            <Settings2 className="h-4 w-4" />
            {showConfig ? "Hide config" : "View config"}
          </Button>
          <Button
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending || isRunning}
            size="default"
          >
            {runMutation.isPending ? (
              <><RefreshCw className="mr-2 h-4 w-4 animate-spin" />Starting…</>
            ) : isRunning ? (
              <><RefreshCw className="mr-2 h-4 w-4 animate-spin" />Running…</>
            ) : (
              <><Play className="mr-2 h-4 w-4" />Run Pipeline</>
            )}
          </Button>
        </div>
      </div>

      {/* Scraping config panel */}
      {showConfig && config && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold">
              <Settings2 className="h-4 w-4" />
              Pipeline configuration
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Save filters here and they will apply on the next pipeline run.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="target-roles">Target roles</Label>
                <Textarea
                  id="target-roles"
                  value={targetRolesText}
                  onChange={(e) => setTargetRolesText(e.target.value)}
                  rows={4}
                  placeholder={"data scientist\nmachine learning engineer\ndata engineer"}
                />
                <p className="text-xs text-muted-foreground">
                  Use one role per line. These are the job titles the scraper will search for.
                </p>
              </div>

              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="locations">Locations</Label>
                <Textarea
                  id="locations"
                  value={locationsText}
                  onChange={(e) => setLocationsText(e.target.value)}
                  rows={5}
                  placeholder={"New York\nSan Francisco\nSeattle\nRemote"}
                />
                <p className="text-xs text-muted-foreground">
                  Use one location per line. Include `Remote` if you want remote roles kept in the search.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="min-salary">Minimum salary</Label>
                <Input
                  id="min-salary"
                  type="number"
                  min={0}
                  value={minSalary}
                  onChange={(e) => setMinSalary(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="posted-within-days">Posted within (days)</Label>
                <Select
                  value={postedWithinDays}
                  onValueChange={(value) => setPostedWithinDays(value ?? "7")}
                >
                  <SelectTrigger id="posted-within-days">
                    <SelectValue placeholder="Select date range" />
                  </SelectTrigger>
                  <SelectContent>
                    {POSTED_WINDOW_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Choose from today through the last 7 days.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="min-h1b-filings">Minimum H1B filings</Label>
                <Input
                  id="min-h1b-filings"
                  type="number"
                  min={0}
                  value={minH1bFilings}
                  onChange={(e) => setMinH1bFilings(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Used when sponsorship filtering is enabled.
                </p>
              </div>

              <div className="flex items-center gap-2 sm:col-span-2">
                <input
                  id="require-sponsorship"
                  type="checkbox"
                  className="h-4 w-4 rounded border-input"
                  checked={requireSponsorship}
                  onChange={(e) => setRequireSponsorship(e.target.checked)}
                />
                <Label htmlFor="require-sponsorship" className="cursor-pointer">
                  Require sponsorship-friendly jobs
                </Label>
              </div>
            </div>

            <div className="rounded-md border bg-muted/30 px-3 py-2">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground mb-1.5">
                Current summary
              </p>
              <FiltersPanel
                filters={{
                  ...config,
                  target_roles: parseListInput(targetRolesText),
                  locations: parseListInput(locationsText),
                  min_salary: Number(minSalary || 0),
                  posted_within_days: Number(postedWithinDays || 7),
                  min_h1b_filings: Number(minH1bFilings || 0),
                  require_sponsorship: requireSponsorship,
                }}
              />
            </div>

            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">
                Company count is read-only because it comes from the supported ATS source lists in code.
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setTargetRolesText(config.target_roles.join("\n"));
                    setLocationsText(config.locations.join("\n"));
                    setMinSalary(String(config.min_salary));
                    setPostedWithinDays(String(config.posted_within_days || 7));
                    setMinH1bFilings(String(config.min_h1b_filings));
                    setRequireSponsorship(config.require_sponsorship);
                  }}
                  disabled={saveConfigMutation.isPending}
                >
                  Reset
                </Button>
                <Button
                  size="sm"
                  onClick={() => saveConfigMutation.mutate()}
                  disabled={saveConfigMutation.isPending}
                >
                  {saveConfigMutation.isPending ? (
                    <><RefreshCw className="mr-2 h-4 w-4 animate-spin" />Saving…</>
                  ) : (
                    "Save config"
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Active run progress card */}
      {activeStatus && (
        <ActiveRunCard
          status={activeStatus}
          onCancel={() => activeRunId && cancelMutation.mutate(activeRunId)}
          cancelling={cancelMutation.isPending}
        />
      )}

      {/* Run history */}
      <div>
        <h2 className="mb-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Run History
        </h2>
        <div className="space-y-2">
          {!runs || runs.length === 0 ? (
            <div className="rounded-lg border border-dashed p-8 text-center">
              <p className="text-sm text-muted-foreground">No runs yet. Click Run Pipeline to start.</p>
            </div>
          ) : (
            [...runs].reverse().map((run) => (
              <RunHistoryRow key={run.run_id} run={run} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
