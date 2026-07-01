import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DonutChart from "../components/DonutChart";

describe("DonutChart", () => {
  it("renders the chart title", () => {
    render(<DonutChart data={{ security: 3, bug: 2 }} title="Issues by Category" />);
    expect(screen.getByText("Issues by Category")).toBeInTheDocument();
  });

  it("shows empty state when data is empty", () => {
    render(<DonutChart data={{}} title="Issues by Category" />);
    expect(screen.getByText("No data yet.")).toBeInTheDocument();
  });

  it("renders without crashing for single entry data", () => {
    render(<DonutChart data={{ security: 10 }} title="Single" />);
    expect(screen.getByText("Single")).toBeInTheDocument();
  });
});
