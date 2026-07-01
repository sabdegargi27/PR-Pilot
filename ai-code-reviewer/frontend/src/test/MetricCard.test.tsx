import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MetricCard from "../components/MetricCard";

describe("MetricCard", () => {
  it("renders label and numeric value", () => {
    render(<MetricCard label="Total Issues" value={42} />);
    expect(screen.getByText("Total Issues")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders string value", () => {
    render(<MetricCard label="Status" value="active" />);
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("renders sub text when provided", () => {
    render(<MetricCard label="PRs" value={5} sub="last 30 days" />);
    expect(screen.getByText("last 30 days")).toBeInTheDocument();
  });

  it("does not render sub element when omitted", () => {
    render(<MetricCard label="PRs" value={5} />);
    expect(screen.queryByText("last 30 days")).not.toBeInTheDocument();
  });

  it("renders zero value correctly", () => {
    render(<MetricCard label="Issues" value={0} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
