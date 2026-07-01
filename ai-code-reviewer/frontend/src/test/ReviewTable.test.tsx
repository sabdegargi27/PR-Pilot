import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import ReviewTable from "../components/ReviewTable";
import type { ReviewSummary } from "../api/client";

const REVIEW_FIXTURE: ReviewSummary[] = [
  {
    id: 1,
    pr_number: 42,
    pr_title: "Add auth feature",
    author: "alice",
    status: "completed",
    created_at: "2024-03-01T12:00:00Z",
    issue_count: 5,
  },
  {
    id: 2,
    pr_number: 43,
    pr_title: "Fix null pointer",
    author: "bob",
    status: "pending",
    created_at: "2024-03-02T12:00:00Z",
    issue_count: 0,
  },
];

describe("ReviewTable", () => {
  it("renders empty state when no reviews", () => {
    render(
      <MemoryRouter>
        <ReviewTable reviews={[]} />
      </MemoryRouter>
    );
    expect(screen.getByText("No reviews yet.")).toBeInTheDocument();
  });

  it("renders a row for each review", () => {
    render(
      <MemoryRouter>
        <ReviewTable reviews={REVIEW_FIXTURE} />
      </MemoryRouter>
    );
    expect(screen.getByText("Add auth feature")).toBeInTheDocument();
    expect(screen.getByText("Fix null pointer")).toBeInTheDocument();
  });

  it("renders PR numbers with hash prefix", () => {
    render(
      <MemoryRouter>
        <ReviewTable reviews={REVIEW_FIXTURE} />
      </MemoryRouter>
    );
    expect(screen.getByText("#42")).toBeInTheDocument();
    expect(screen.getByText("#43")).toBeInTheDocument();
  });

  it("renders status badges", () => {
    render(
      <MemoryRouter>
        <ReviewTable reviews={REVIEW_FIXTURE} />
      </MemoryRouter>
    );
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("pending")).toBeInTheDocument();
  });

  it("renders issue counts", () => {
    render(
      <MemoryRouter>
        <ReviewTable reviews={REVIEW_FIXTURE} />
      </MemoryRouter>
    );
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
