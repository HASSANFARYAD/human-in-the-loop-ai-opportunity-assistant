import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Opportunity, BatchScoreResult } from "@/types/api";

const mockGet = vi.fn();
vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: mockGet }),
  useRouter: () => ({ replace: vi.fn() }),
}));

const mockQueryState = { data: [] as Opportunity[], isLoading: false, isError: false };
const mockInvalidateQueries = vi.fn();
vi.mock("@tanstack/react-query", () => ({
  useQuery: () => mockQueryState,
  useMutation: ({ mutationFn, onSuccess, onError }: any) => ({
    mutate: async (...args: any[]) => {
      try {
        const data = await mutationFn(...args);
        onSuccess?.(data);
      } catch (e) {
        onError?.(e);
      }
    },
    isPending: false,
    variables: undefined,
  }),
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));

vi.mock("@/services/opportunity.service", () => ({
  opportunityService: {
    list: vi.fn(),
    score: vi.fn(),
    remove: vi.fn(),
    scoreBatch: vi.fn(),
  },
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
    span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
    circle: ({ children, ...props }: any) => <circle {...props}>{children}</circle>,
    text: ({ children, ...props }: any) => <text {...props}>{children}</text>,
    tbody: ({ children, ...props }: any) => <tbody {...props}>{children}</tbody>,
    tr: ({ children, ...props }: any) => <tr {...props}>{children}</tr>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

import { OpportunityListView } from "@/features/opportunities/opportunity-list-view";
import { opportunityService } from "@/services/opportunity.service";

function makeJob(overrides: Partial<Opportunity> = {}): Opportunity {
  return {
    id: 1, title: "Software Engineer", company: "Tech Corp",
    location: "Remote", source: "Manual", description: "desc",
    classification: "job", match_score: 85, status: "new",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-15T00:00:00Z",
    ...overrides,
  };
}

describe("OpportunityListView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.confirm = vi.fn(() => true);
    mockGet.mockReturnValue(null);
    mockQueryState.data = [];
    mockQueryState.isLoading = false;
    mockQueryState.isError = false;
  });

  it("renders the page title", () => {
    render(<OpportunityListView />);
    expect(screen.getByText("All Jobs")).toBeTruthy();
  });

  it("shows empty state when no jobs", () => {
    render(<OpportunityListView />);
    expect(screen.getByText("No jobs saved yet")).toBeTruthy();
  });

  it("renders job list in table", () => {
    mockQueryState.data = [
      makeJob({ id: 1, title: "Frontend Dev", company: "Web Co", match_score: 90 }),
      makeJob({ id: 2, title: "Backend Dev", company: "API Inc", match_score: 70 }),
    ];
    render(<OpportunityListView />);

    expect(screen.getByText("Frontend Dev")).toBeTruthy();
    expect(screen.getByText("Backend Dev")).toBeTruthy();
    expect(screen.getByText(/Web Co/)).toBeTruthy();
    expect(screen.getByText(/API Inc/)).toBeTruthy();
  });

  it("filters jobs by search query", async () => {
    mockQueryState.data = [
      makeJob({ id: 1, title: "Frontend Dev", company: "Web Co" }),
      makeJob({ id: 2, title: "Backend Dev", company: "API Inc" }),
    ];
    render(<OpportunityListView />);

    const searchInput = screen.getByPlaceholderText(/Search by title/);
    await userEvent.type(searchInput, "Frontend");

    expect(screen.getByText("Frontend Dev")).toBeTruthy();
    expect(screen.queryByText("Backend Dev")).toBeNull();
  });

  it("shows 2 results count", () => {
    mockQueryState.data = [makeJob({ id: 1 }), makeJob({ id: 2 })];
    render(<OpportunityListView />);
    expect(screen.getByText("2 results")).toBeTruthy();
  });

  it("calls score mutation when Score button clicked", async () => {
    vi.mocked(opportunityService.score).mockResolvedValueOnce({ classification: "job" });
    mockQueryState.data = [makeJob({ id: 1 })];

    render(<OpportunityListView />);

    const scoreButtons = screen.getAllByRole("button", { name: /Score$/ });
    fireEvent.click(scoreButtons[0]);

    await waitFor(() => {
      expect(opportunityService.score).toHaveBeenCalledWith(1);
    });
  });

  it("calls delete mutation when Delete button clicked and confirmed", async () => {
    vi.mocked(opportunityService.remove).mockResolvedValueOnce({ status: "deleted" });
    mockQueryState.data = [makeJob({ id: 1, title: "Job to delete" })];

    render(<OpportunityListView />);

    const deleteButtons = screen.getAllByRole("button", { name: /Delete/ });
    fireEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(opportunityService.remove).toHaveBeenCalledWith(1);
    });
  });

  it("shows review title when reviewOnly is true", () => {
    render(<OpportunityListView reviewOnly />);
    expect(screen.getByText("Review Jobs")).toBeTruthy();
  });

  it("renders filter selects", () => {
    mockQueryState.data = [makeJob()];
    render(<OpportunityListView />);

    expect(screen.getByLabelText("Job type filter")).toBeTruthy();
    expect(screen.getByLabelText("Status filter")).toBeTruthy();
  });

  it("supports pagination", () => {
    const jobs = Array.from({ length: 15 }, (_, i) =>
      makeJob({ id: i + 1, title: `Job ${i + 1}` }),
    );
    mockQueryState.data = jobs;
    render(<OpportunityListView />);

    expect(screen.getByText("Page 1 of 2")).toBeTruthy();
    expect(screen.getByText("Next")).toBeTruthy();
  });

  it("shows batch score panel when selected jobs are scored", async () => {
    const batchResult: BatchScoreResult = {
      status: "ok", total: 2, succeeded: 2, scored: 2, skipped: 0, failed: 0,
      results: [{ job_id: 1, status: "success" }, { job_id: 2, status: "success" }],
    };
    vi.mocked(opportunityService.scoreBatch).mockResolvedValueOnce(batchResult);
    mockQueryState.data = [
      makeJob({ id: 1, title: "Job A", match_score: null }),
      makeJob({ id: 2, title: "Job B", match_score: null }),
    ];

    render(<OpportunityListView />);

    const jobCheckboxes = screen.getAllByRole("checkbox").filter(
      (cb) => cb.getAttribute("aria-label")?.startsWith("Select"),
    );
    fireEvent.click(jobCheckboxes[0]);
    fireEvent.click(jobCheckboxes[1]);

    fireEvent.click(screen.getByText("Score selected jobs"));

    await waitFor(() => {
      const badges = screen.getAllByText(/Scored/);
      expect(badges.length).toBeGreaterThan(0);
    });
  });
});
