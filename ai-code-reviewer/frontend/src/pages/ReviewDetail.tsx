import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { fetchReview, type ReviewDetail as ReviewDetailType } from "../api/client";

const CATEGORY_COLORS: Record<string, string> = {
  security: "bg-red-100 text-red-700",
  bug: "bg-orange-100 text-orange-700",
  performance: "bg-yellow-100 text-yellow-700",
  architecture: "bg-purple-100 text-purple-700",
  style: "bg-blue-100 text-blue-700",
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-500 text-white",
  warning: "bg-yellow-400 text-yellow-900",
  info: "bg-blue-100 text-blue-700",
};

export default function ReviewDetail() {
  const { reviewId } = useParams<{ reviewId: string }>();
  const [review, setReview] = useState<ReviewDetailType | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!reviewId) return;
    fetchReview(Number(reviewId))
      .then(setReview)
      .finally(() => setLoading(false));
  }, [reviewId]);

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <Link to="/" className="text-indigo-600 hover:underline text-sm mb-4 inline-block">
        ← Dashboard
      </Link>

      {loading ? (
        <p className="text-gray-400">Loading…</p>
      ) : !review ? (
        <p className="text-gray-400">Review not found.</p>
      ) : (
        <>
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-gray-900">
              PR #{review.pr_number}: {review.pr_title}
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              by <span className="font-medium">{review.author}</span> &mdash;{" "}
              {new Date(review.created_at).toLocaleString()}
            </p>
          </div>

          {review.comments.length === 0 ? (
            <div className="rounded-2xl bg-white shadow p-8 text-center text-gray-400">
              No issues found — great code!
            </div>
          ) : (
            <div className="space-y-4">
              {review.comments.map((c) => (
                <div key={c.id} className="rounded-2xl bg-white shadow p-5">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                        CATEGORY_COLORS[c.category] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {c.category}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                        SEVERITY_COLORS[c.severity] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {c.severity}
                    </span>
                    <span className="text-xs text-gray-400 font-mono ml-auto">
                      {c.file_path}:{c.line_number}
                    </span>
                  </div>
                  <p className="text-gray-800 text-sm">{c.comment}</p>
                  {c.suggestion && (
                    <pre className="mt-3 bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs text-gray-700 overflow-x-auto whitespace-pre-wrap">
                      {c.suggestion}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
