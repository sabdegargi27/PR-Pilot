import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SeverityTrendChart from "../components/SeverityTrendChart";
import type { TrendPoint } from "../api/client";

const TREND_FIXTURE: TrendPoint[] = [
  {
    review_id: 1,
    pr_number: 1,
    created_at: "2024-01-01T10:00:00Z",
    by_severity: { critical: 2, warning: 1, info: 3 },
  },
  {
    review_id: 2,
    pr_number: 2,
    created_at: "2024-01-02T10:00:00Z",
    by_severity: { critical: 0, warning: 4, info: 1 },
  },
];

describe("SeverityTrendChart", () => {
  it("renders the default title", () => {
    render(<SeverityTrendChart trend={TREND_FIXTURE} />);
    expect(screen.getByText("Severity Trend Over Time")).toBeInTheDocument();
  });

  it("renders a custom title", () => {
    render(<SeverityTrendChart trend={TREND_FIXTURE} title="My Custom Title" />);
    expect(screen.getByText("My Custom Title")).toBeInTheDocument();
  });

  it("shows empty state when trend is empty", () => {
    render(<SeverityTrendChart trend={[]} />);
    expect(screen.getByText("No trend data yet.")).toBeInTheDocument();
  });

  it("renders without crashing for single data point", () => {
    render(<SeverityTrendChart trend={[TREND_FIXTURE[0]]} />);
    expect(screen.getByText("Severity Trend Over Time")).toBeInTheDocument();
  });
});
