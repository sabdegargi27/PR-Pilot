import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendPoint } from "../api/client";

interface SeverityTrendChartProps {
  trend: TrendPoint[];
  title?: string;
}

interface ChartRow {
  label: string;
  critical: number;
  warning: number;
  info: number;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#ef4444",
  warning: "#f59e0b",
  info: "#3b82f6",
};

export default function SeverityTrendChart({
  trend,
  title = "Severity Trend Over Time",
}: SeverityTrendChartProps) {
  if (trend.length === 0) {
    return (
      <div className="rounded-2xl bg-white shadow p-6 flex items-center justify-center h-56">
        <p className="text-sm text-gray-400">No trend data yet.</p>
      </div>
    );
  }

  const chartData: ChartRow[] = trend.map((point) => ({
    label: `PR #${point.pr_number}`,
    critical: point.by_severity["critical"] ?? 0,
    warning: point.by_severity["warning"] ?? 0,
    info: point.by_severity["info"] ?? 0,
  }));

  return (
    <div className="rounded-2xl bg-white shadow p-6">
      <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-4">
        {title}
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 0, right: 8, left: -10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
          <Tooltip />
          <Legend />
          {(["critical", "warning", "info"] as const).map((sev) => (
            <Line
              key={sev}
              type="monotone"
              dataKey={sev}
              stroke={SEVERITY_COLORS[sev]}
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
