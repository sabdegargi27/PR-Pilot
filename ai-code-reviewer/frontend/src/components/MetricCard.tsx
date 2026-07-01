interface MetricCardProps {
  label: string;
  value: number | string;
  sub?: string;
}

export default function MetricCard({ label, value, sub }: MetricCardProps) {
  return (
    <div className="rounded-2xl bg-white shadow p-6 flex flex-col gap-1">
      <span className="text-sm text-gray-500 font-medium uppercase tracking-wide">
        {label}
      </span>
      <span className="text-4xl font-bold text-gray-900">{value}</span>
      {sub && <span className="text-xs text-gray-400">{sub}</span>}
    </div>
  );
}
