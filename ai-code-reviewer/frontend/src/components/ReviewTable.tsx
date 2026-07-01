import { Link } from "react-router-dom";
import type { ReviewSummary } from "../api/client";

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-green-100 text-green-700",
  pending: "bg-gray-100 text-gray-600",
  failed: "bg-red-100 text-red-700",
};

interface ReviewTableProps {
  reviews: ReviewSummary[];
}

export default function ReviewTable({ reviews }: ReviewTableProps) {
  if (reviews.length === 0) {
    return (
      <p className="text-gray-400 text-sm py-6 text-center">No reviews yet.</p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl shadow">
      <table className="min-w-full bg-white text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500 uppercase text-xs tracking-wide">
            <th className="px-4 py-3">PR</th>
            <th className="px-4 py-3">Title</th>
            <th className="px-4 py-3">Author</th>
            <th className="px-4 py-3">Issues</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Date</th>
          </tr>
        </thead>
        <tbody>
          {reviews.map((r) => (
            <tr key={r.id} className="border-b hover:bg-gray-50 transition-colors">
              <td className="px-4 py-3 font-mono text-gray-500">#{r.pr_number}</td>
              <td className="px-4 py-3">
                <Link
                  to={`/reviews/${r.id}`}
                  className="text-indigo-600 hover:underline font-medium"
                >
                  {r.pr_title}
                </Link>
              </td>
              <td className="px-4 py-3 text-gray-600">{r.author}</td>
              <td className="px-4 py-3">
                <span className="font-semibold text-gray-800">{r.issue_count}</span>
              </td>
              <td className="px-4 py-3">
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    STATUS_COLORS[r.status] ?? "bg-gray-100 text-gray-600"
                  }`}
                >
                  {r.status}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-400">
                {new Date(r.created_at).toLocaleDateString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
