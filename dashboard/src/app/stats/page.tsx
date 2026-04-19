"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchStats } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

const COLORS = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#3b82f6", "#8b5cf6"];

function StatCard({
  title,
  value,
  sub,
}: {
  title: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

export default function StatsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
  });

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
    );
  }

  if (!data) return <p className="text-muted-foreground">No stats available.</p>;

  const { jobs, match, by_source, by_h1b_tier, config } = data;
  const minSalaryLabel = `$${(config.min_salary / 1000).toFixed(0)}k`;

  const statusData = [
    { name: "New", count: jobs.new_jobs },
    { name: "Reviewing", count: jobs.reviewing_jobs },
    { name: "Applied", count: jobs.applied_jobs },
    { name: "Interview", count: jobs.interview_jobs },
    { name: "Offer", count: jobs.offer_jobs },
    { name: "Rejected", count: jobs.rejected_jobs },
  ].filter((d) => d.count > 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Stats</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Database-wide totals. Pipeline config changes affect these after the next successful run.
        </p>
      </div>

      {/* KPI cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="Total Jobs" value={jobs.total_jobs} />
        <StatCard
          title="H1B Sponsors"
          value={jobs.sponsoring_jobs}
          sub={`${((jobs.sponsoring_jobs / jobs.total_jobs) * 100).toFixed(0)}% of jobs`}
        />
        <StatCard
          title="High Salary"
          value={jobs.high_salary_jobs}
          sub={`≥ ${minSalaryLabel}`}
        />
        <StatCard title="Companies" value={jobs.unique_companies} />
        <StatCard title="Matched" value={match.total_matched} />
        <StatCard
          title="Avg Match Score"
          value={`${match.avg_combined_score.toFixed(0)}%`}
        />
        <StatCard title="Strong Matches" value={match.strong_matches} />
        <StatCard
          title="Last Scraped"
          value={
            jobs.last_scraped_at
              ? new Date(jobs.last_scraped_at).toLocaleDateString()
              : "—"
          }
        />
      </div>

      {/* Charts row */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* By status */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-sm">Jobs by Status</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={statusData} layout="vertical" margin={{ left: 10 }}>
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis
                  dataKey="name"
                  type="category"
                  tick={{ fontSize: 11 }}
                  width={70}
                />
                <Tooltip />
                <Bar dataKey="count" fill="#6366f1" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* By source */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-sm">Jobs by Source</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={by_source.map((s) => ({ name: s.source, value: s.count }))}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={70}
                  label={({ name, percent }: { name?: string; percent?: number }) =>
                    `${name ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`
                  }
                  labelLine={false}
                >
                  {by_source.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Match tier breakdown */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-sm">Match Tiers</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={[
                    { name: "Strong", value: match.strong_matches },
                    { name: "Good", value: match.good_matches },
                    { name: "Stretch", value: match.stretch_matches },
                  ]}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={70}
                >
                  {["#22c55e", "#3b82f6", "#f59e0b"].map((c, i) => (
                    <Cell key={i} fill={c} />
                  ))}
                </Pie>
                <Legend />
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* H1B tier table */}
      {by_h1b_tier && by_h1b_tier.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">H1B Sponsorship Tiers</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {by_h1b_tier.map(({ tier, count }) => (
                <div key={tier} className="flex items-center gap-3">
                  <span className="w-48 text-sm">{tier}</span>
                  <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full"
                      style={{ width: `${(count / jobs.total_jobs) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm text-muted-foreground w-10 text-right">{count}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
