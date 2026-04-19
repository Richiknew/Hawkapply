"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { fetchMatches, runMatching, fetchMatchRunStatus } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ExternalLink, Play, RefreshCw } from "lucide-react";
import { toast } from "sonner";

const TIER_COLORS: Record<string, string> = {
  "Strong Match": "bg-green-100 text-green-800",
  "Good Match": "bg-blue-100 text-blue-800",
  "Stretch Match": "bg-yellow-100 text-yellow-800",
};


export default function MatchesPage() {
  const [tierFilter, setTierFilter] = useState<string>("all");
  const [runId, setRunId] = useState<string | null>(null);

  const { data: matches, isLoading, refetch } = useQuery({
    queryKey: ["matches", tierFilter],
    queryFn: () =>
      fetchMatches({
        tier: tierFilter !== "all" ? tierFilter : undefined,
        limit: 100,
      }),
  });

  const { data: runStatus } = useQuery({
    queryKey: ["matchRun", runId],
    queryFn: () => fetchMatchRunStatus(runId!),
    enabled: !!runId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" ? 2000 : false;
    },
  });

  const runMutation = useMutation({
    mutationFn: (aiThreshold?: number) => runMatching(aiThreshold, 100),
    onSuccess: (data) => {
      setRunId(data.run_id);
      toast.info("Matching started…");
    },
    onError: () => toast.error("Failed to start matching"),
  });

  if (runStatus?.status === "completed" && runId) {
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Matches</h1>
        <div className="flex items-center gap-3">
          {runStatus?.status === "running" && (
            <span className="flex items-center gap-1 text-sm text-muted-foreground">
              <RefreshCw className="h-3 w-3 animate-spin" />
              Matching {runStatus.matched}/{runStatus.total}…
            </span>
          )}
          {runStatus?.status === "completed" && (
            <span className="text-sm text-green-600">
              Done — {runStatus.matched} matched
            </span>
          )}
          <Button
            size="sm"
            onClick={() => runMutation.mutate(0.6)}
            disabled={runMutation.isPending || runStatus?.status === "running"}
          >
            <Play className="mr-1 h-3 w-3" />
            Run Matching
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Select value={tierFilter} onValueChange={(v) => setTierFilter(v ?? "all")}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Tier" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All tiers</SelectItem>
            <SelectItem value="strong">Strong</SelectItem>
            <SelectItem value="good">Good</SelectItem>
            <SelectItem value="stretch">Stretch</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-sm text-muted-foreground">
          {matches?.length ?? 0} results
        </span>
      </div>

      {isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-48 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {matches?.map((match) => (
            <Card key={match.id} className="flex flex-col">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-sm font-semibold leading-snug">
                    {match.title}
                  </CardTitle>
                  <a href={match.url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-4 w-4 shrink-0 text-muted-foreground hover:text-foreground" />
                  </a>
                </div>
                <p className="text-xs text-muted-foreground">{match.company}</p>
              </CardHeader>

              <CardContent className="flex flex-col gap-3 flex-1">
                <div className="flex items-center gap-2">
                  <Badge className={`text-xs ${TIER_COLORS[match.fit_tier] ?? "bg-gray-100 text-gray-800"}`}>
                    {match.fit_tier}
                  </Badge>
                  <span className="ml-auto text-lg font-bold">
                    {match.combined_score.toFixed(0)}%
                  </span>
                </div>

                <div className="flex gap-3 text-xs text-muted-foreground">
                  <span>Match: {match.match_score.toFixed(0)}%</span>
                  <span>H1B: {match.h1b_score.toFixed(0)}%</span>
                  {match.sponsors_h1b && (
                    <span className="text-emerald-600">Sponsor ✓</span>
                  )}
                </div>

                {match.strengths && match.strengths.length > 0 && (
                  <div className="space-y-1">
                    {match.strengths.slice(0, 2).map((s, i) => (
                      <p key={i} className="text-xs text-muted-foreground line-clamp-1">
                        ✓ {s}
                      </p>
                    ))}
                  </div>
                )}

                {match.gaps && match.gaps.length > 0 && (
                  <div className="space-y-1">
                    {match.gaps.slice(0, 1).map((g, i) => (
                      <p key={i} className="text-xs text-muted-foreground line-clamp-1">
                        ✗ {g}
                      </p>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
