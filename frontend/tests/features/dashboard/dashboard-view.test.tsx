import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Opportunity } from "@/types/api";

const mockState = { data: [] as Opportunity[], isLoading: false, isError: false };

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => mockState,
}));

vi.mock("@/services/opportunity.service", () => ({
  opportunityService: { list: vi.fn() },
}));

vi.mock("@/components/charts/analytics-charts", () => ({
  SourceChart: () => <div data-testid="source-chart" />,
  ScoreDistribution: () => <div data-testid="score-distribution" />,
  TrendChart: () => <div data-testid="trend-chart" />,
}));

vi.mock("@/components/ui/next-best-action", () => ({
  NextBestAction: ({ unscoredCount, totalJobs }: any) =>
    totalJobs === 0
      ? <div data-testid="next-best-action">Find your first jobs</div>
      : unscoredCount > 0
        ? <div data-testid="next-best-action">Score {unscoredCount} jobs</div>
        : null,
}));

vi.mock("@/components/ui/skeleton", () => ({
  Skeleton: () => <div data-testid="skeleton" />,
  SkeletonKPIRow: () => <div data-testid="skeleton-kpi-row" />,
  SkeletonChart: () => <div data-testid="skeleton-chart" />,
}));

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
    button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
  },
}));

import { DashboardView } from "@/features/dashboard/dashboard-view";

function makeJob(overrides: Partial<Opportunity> = {}): Opportunity {
  return {
    id: 1, title: "Test Job", company: "Test Co", source: "Manual", description: "desc",
    ...overrides,
  };
}

describe("DashboardView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockState.data = [];
    mockState.isLoading = false;
    mockState.isError = false;
  });

  it("renders dashboard title and description", () => {
    render(<DashboardView />);
    expect(screen.getByText("Dashboard")).toBeTruthy();
    expect(screen.getByText(/Track saved jobs/)).toBeTruthy();
  });

  it("renders KPI cards with job data", () => {
    mockState.data = [
      makeJob({ match_score: 85 }),
      makeJob({ id: 2, title: "Job 2", match_score: 45, status: "review", deadline: "2026-07-01" }),
    ];
    render(<DashboardView />);

    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("Saved Jobs")).toBeTruthy();
    expect(screen.getByText("High Match (80+)")).toBeTruthy();
  });

  it("shows KPI for items needing review", () => {
    mockState.data = [
      makeJob({ status: "needs review" }),
      makeJob({ id: 2, status: "reviewed" }),
    ];
    render(<DashboardView />);

    expect(screen.getByText("Need Review")).toBeTruthy();
  });

  it("shows NextBestAction when unscored jobs exist", () => {
    mockState.data = [makeJob({ match_score: null, score: null })];
    render(<DashboardView />);
    expect(screen.getByTestId("next-best-action")).toBeTruthy();
  });

  it("renders chart components", () => {
    mockState.data = [makeJob({ created_at: "2026-06-29T12:00:00Z" })];
    render(<DashboardView />);
    expect(screen.getByTestId("source-chart")).toBeTruthy();
    expect(screen.getByTestId("score-distribution")).toBeTruthy();
    expect(screen.getByTestId("trend-chart")).toBeTruthy();
  });

  it("shows loading skeleton when isLoading is true", () => {
    mockState.isLoading = true;
    render(<DashboardView />);

    expect(screen.getByTestId("skeleton")).toBeTruthy();
    expect(screen.getByTestId("skeleton-kpi-row")).toBeTruthy();
    expect(screen.getAllByTestId("skeleton-chart").length).toBe(3);
  });

  it("shows error message on fetch error", () => {
    mockState.isError = true;
    render(<DashboardView />);

    expect(screen.getByText(/Some dashboard data could not be loaded/)).toBeTruthy();
  });

  it("shows upcoming deadlines with urgent count", () => {
    mockState.data = [
      makeJob({ deadline: "2026-07-15" }),
      makeJob({ id: 2, deadline: "2026-08-01" }),
    ];
    render(<DashboardView />);

    expect(screen.getByText("Upcoming Deadlines")).toBeTruthy();
  });
});
