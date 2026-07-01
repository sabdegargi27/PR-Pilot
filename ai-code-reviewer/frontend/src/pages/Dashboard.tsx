import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchMetrics,
  fetchRepos,
  type Metrics,
  type Repo,
  type TrendPoint,
} from "../api/client";
import DonutChart from "../components/DonutChart";
import MetricCard from "../components/MetricCard";
import SeverityTrendChart from "../components/SeverityTrendChart";

interface AggregatedMetrics {
  totalRepos: number;
  totalPRs: number;
  totalIssues: number;
  byCategory: Record<string, number>;
  trend: TrendPoint[];
}

function aggregateMetrics(repos: Repo[], allMetrics: Metrics[]): AggregatedMetrics {
  const byCategory: Record<string, number> = {};
  let totalIssues = 0;
  const trend: TrendPoint[] = [];

  allMetrics.forEach((m) => {
    totalIssues += m.total;
    for (const [cat, count] of Object.entries(m.by_category)) {
      byCategory[cat] = (byCategory[cat] ?? 0) + count;
    }
    trend.push(...m.trend);
  });

  // Sort trend chronologically across all repos
  trend.sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

  return {
    totalRepos: repos.length,
    totalPRs: trend.length,
    totalIssues,
    byCategory,
    trend,
  };
}

export default function Dashboard() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [aggregated, setAggregated] = useState<AggregatedMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchRepos()
      .then(async (repoList) => {
        setRepos(repoList);
        if (repoList.length === 0) {
          setAggregated({
            totalRepos: 0,
            totalPRs: 0,
            totalIssues: 0,
            byCategory: {},
            trend: [],
          });
          return;
        }
        const metricsList = await Promise.all(
          repoList.map((r) => fetchMetrics(r.full_name))
        );
        setAggregated(aggregateMetrics(repoList, metricsList));
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">AI Code Reviewer</h1>
        <p className="text-gray-500 mt-1">
          Automated pull-request analysis powered by LLMs
        </p>
      </header>

      {loading ? (
        <p className="text-gray-400">Loading…</p>
      ) : (
        <>
          {/* Summary metric cards */}
          <div className="grid gap-4 sm:grid-cols-3 mb-6">
            <MetricCard label="Repositories" value={aggregated?.totalRepos ?? 0} />
            <MetricCard label="PRs Reviewed" value={aggregated?.totalPRs ?? 0} />
            <MetricCard label="Total Issues" value={aggregated?.totalIssues ?? 0} />
          </div>

          {/* Charts row */}
          {aggregated && (
            <div className="grid gap-4 md:grid-cols-2 mb-8">
              <DonutChart
                data={aggregated.byCategory}
                title="Issues by Category"
              />
              <SeverityTrendChart
                trend={aggregated.trend}
                title="Severity Trend Over Time"
              />
            </div>
          )}

          {/* Repository list */}
          <h2 className="text-lg font-semibold text-gray-700 mb-3">
            Tracked Repositories
          </h2>
          {repos.length === 0 ? (
            <div className="rounded-2xl bg-white shadow p-8 text-center text-gray-400">
              <p className="text-lg font-medium">No repositories tracked yet.</p>
              <p className="text-sm mt-1">
                Install the GitHub webhook to start reviewing pull requests.
              </p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {repos.map((repo) => (
                <Link
                  key={repo.id}
                  to={`/repos/${encodeURIComponent(repo.full_name)}`}
                  className="rounded-2xl bg-white shadow p-6 hover:shadow-md transition-shadow"
                >
                  <p className="font-semibold text-gray-800 truncate">
                    {repo.full_name}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    Since {new Date(repo.installed_at).toLocaleDateString()}
                  </p>
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
