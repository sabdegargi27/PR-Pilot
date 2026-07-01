import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchMetrics,
  fetchReviews,
  type Metrics,
  type PaginatedReviews,
} from "../api/client";
import DonutChart from "../components/DonutChart";
import IssueChart from "../components/IssueChart";
import MetricCard from "../components/MetricCard";
import ReviewTable from "../components/ReviewTable";
import SeverityTrendChart from "../components/SeverityTrendChart";

export default function RepoDetail() {
  const { repoName } = useParams<{ repoName: string }>();
  const decoded = decodeURIComponent(repoName ?? "");

  const [reviews, setReviews] = useState<PaginatedReviews | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!decoded) return;
    setLoading(true);
    Promise.all([fetchReviews(decoded, page), fetchMetrics(decoded)])
      .then(([rev, met]) => {
        setReviews(rev);
        setMetrics(met);
      })
      .finally(() => setLoading(false));
  }, [decoded, page]);

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <Link to="/" className="text-indigo-600 hover:underline text-sm mb-4 inline-block">
        ← All Repositories
      </Link>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">{decoded}</h1>

      {loading ? (
        <p className="text-gray-400">Loading…</p>
      ) : (
        <>
          {metrics && (
            <div className="mb-8">
              <div className="grid gap-4 sm:grid-cols-3 mb-6">
                <MetricCard label="Total Issues" value={metrics.total} />
                <MetricCard
                  label="Critical"
                  value={metrics.by_severity["critical"] ?? 0}
                />
                <MetricCard
                  label="PRs Reviewed"
                  value={reviews?.total ?? 0}
                />
              </div>
              <div className="grid gap-4 md:grid-cols-2 mb-4">
                <DonutChart data={metrics.by_category} title="Issues by Category" />
                <IssueChart
                  data={metrics.by_severity}
                  title="Issues by Severity"
                  colors={["#ef4444", "#f59e0b", "#3b82f6"]}
                />
              </div>
              <SeverityTrendChart trend={metrics.trend} />
            </div>
          )}

          {reviews && (
            <>
              <ReviewTable reviews={reviews.items} />
              <div className="flex items-center justify-between mt-4 text-sm text-gray-500">
                <span>
                  Page {reviews.page} of{" "}
                  {Math.ceil(reviews.total / reviews.page_size)}
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={page === 1}
                    onClick={() => setPage((p) => p - 1)}
                    className="px-3 py-1 rounded bg-white shadow disabled:opacity-40"
                  >
                    Prev
                  </button>
                  <button
                    disabled={page * reviews.page_size >= reviews.total}
                    onClick={() => setPage((p) => p + 1)}
                    className="px-3 py-1 rounded bg-white shadow disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
