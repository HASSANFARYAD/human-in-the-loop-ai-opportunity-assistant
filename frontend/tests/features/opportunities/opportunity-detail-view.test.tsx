import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { Opportunity } from "@/types/api";

const mockParams = { id: "1" };
vi.mock("next/navigation", () => ({
  useParams: () => mockParams,
  useRouter: () => ({ replace: vi.fn() }),
}));

const mockQueries: Record<string, any> = {};
vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryKey }: { queryKey: string[] }) => {
    const key = queryKey[0];
    return mockQueries[key] ?? { data: undefined, isLoading: false };
  },
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
  }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/services/opportunity.service", () => ({
  opportunityService: {
    detail: vi.fn(),
    materials: vi.fn(),
    resumeReviews: vi.fn(),
    interviewPrepSessions: vi.fn(),
    recordings: vi.fn(),
    profiles: vi.fn(),
    resumeTemplates: vi.fn(),
    score: vi.fn(),
    scoreFeedback: vi.fn(),
    generateMaterials: vi.fn(),
    tailorResume: vi.fn(),
    interviewPrep: vi.fn(),
    buildResumeDocument: vi.fn(),
    uploadRecording: vi.fn(),
    updateStatus: vi.fn(),
    remove: vi.fn(),
  },
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
    button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

vi.mock("@/features/opportunities/components/resume-preview", () => ({
  ResumePreview: () => <div data-testid="resume-preview" />,
}));

vi.mock("@/features/opportunities/components/cover-letter-preview", () => ({
  CoverLetterPreview: () => <div data-testid="cover-letter-preview" />,
}));

import { OpportunityDetailView } from "@/features/opportunities/opportunity-detail-view";
import { opportunityService } from "@/services/opportunity.service";

const mockJob: Opportunity = {
  id: 1,
  title: "Senior Engineer",
  company: "Acme Corp",
  location: "Remote",
  source: "Manual",
  description: "A challenging engineering role",
  classification: "job",
  match_score: 85,
  status: "new",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-15T00:00:00Z",
};

describe("OpportunityDetailView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockQueries["opportunity"] = { data: mockJob, isLoading: false };
    mockQueries["materials"] = { data: {} };
    mockQueries["interview-prep"] = { data: [] };
    mockQueries["resume-reviews"] = { data: [] };
    mockQueries["recordings"] = { data: [] };
    mockQueries["profiles"] = { data: [] };
    mockQueries["resume-templates"] = { data: [] };
  });

  it("renders job title and metadata", () => {
    render(<OpportunityDetailView />);

    expect(screen.getByText("Senior Engineer")).toBeTruthy();
    expect(screen.getByText(/Acme Corp/)).toBeTruthy();
    expect(screen.getByText("Manual")).toBeTruthy();
  });

  it("renders all tab triggers", () => {
    render(<OpportunityDetailView />);

    expect(screen.getByRole("tab", { name: "Description" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "AI Evaluation" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Tailored Resume" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Application Materials" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Interview Prep" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Notes" })).toBeTruthy();
  });

  it("shows loading skeleton when job is loading", () => {
    mockQueries["opportunity"] = { data: undefined, isLoading: true };
    const { container } = render(<OpportunityDetailView />);

    const skeletons = container.querySelectorAll("[class*='animate-shimmer']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows job description in default tab", () => {
    render(<OpportunityDetailView />);

    expect(screen.getByText("A challenging engineering role")).toBeTruthy();
  });

  it("shows match score in sidebar", () => {
    render(<OpportunityDetailView />);

    expect(screen.getByText("Match score")).toBeTruthy();
  });

  it("shows Apply button when job has url", () => {
    const jobWithUrl = { ...mockJob, url: "https://example.com/job" };
    mockQueries["opportunity"] = { data: jobWithUrl, isLoading: false };

    render(<OpportunityDetailView />);

    const links = screen.getAllByRole("link").filter((l) => l.getAttribute("href") === "https://example.com/job");
    expect(links.length).toBe(1);
  });

  it("shows profile selector when multiple profiles exist", () => {
    mockQueries["profiles"] = {
      data: [
        { id: 1, name: "Default", is_default: 1 },
        { id: 2, name: "Technical", is_default: 0 },
      ],
    };

    render(<OpportunityDetailView />);

    expect(screen.getByText("Technical")).toBeTruthy();
  });

  it("calls score mutation on Refresh AI score click", async () => {
    vi.mocked(opportunityService.score).mockResolvedValueOnce({});
    render(<OpportunityDetailView />);

    fireEvent.click(screen.getByText("Refresh AI score"));

    await waitFor(() => {
      expect(opportunityService.score).toHaveBeenCalledWith(1, undefined);
    });
  });

  it("calls scoreFeedback on thumbs up", async () => {
    vi.mocked(opportunityService.scoreFeedback).mockResolvedValueOnce({});
    render(<OpportunityDetailView />);

    fireEvent.click(screen.getByLabelText("Mark relevant"));

    await waitFor(() => {
      expect(opportunityService.scoreFeedback).toHaveBeenCalledWith(1, "relevant");
    });
  });

  it("calls delete mutation on Delete job click", async () => {
    vi.mocked(opportunityService.remove).mockResolvedValueOnce({});
    const origConfirm = window.confirm;
    window.confirm = vi.fn(() => true);

    render(<OpportunityDetailView />);

    fireEvent.click(screen.getByText("Delete job"));

    await waitFor(() => {
      expect(opportunityService.remove).toHaveBeenCalledWith(1);
    });

    window.confirm = origConfirm;
  });

  it("shows history dates", () => {
    render(<OpportunityDetailView />);

    expect(screen.getByText(/Created/)).toBeTruthy();
    expect(screen.getByText(/Updated/)).toBeTruthy();
  });

  it("shows deadline info when present", () => {
    const jobWithDeadline = { ...mockJob, deadline: "2026-07-01T00:00:00Z" };
    mockQueries["opportunity"] = { data: jobWithDeadline, isLoading: false };

    render(<OpportunityDetailView />);

    expect(screen.getByText("Jul 1, 2026")).toBeTruthy();
  });
});
