import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Opportunity, BatchScoreResult, TailoredResume, Profile, Recording, Reminder } from "@/types/api";

vi.mock("@/services/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getJson: vi.fn(),
}));

import { opportunityService } from "@/services/opportunity.service";
import { apiClient, getJson } from "@/services/client";

const mockJob: Opportunity = {
  id: 1,
  title: "Senior Engineer",
  company: "Acme Corp",
  location: "Remote",
  remote_type: "Remote",
  source: "Manual",
  description: "A great job",
  match_score: 85,
  classification: "job",
};

describe("opportunityService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("list", () => {
    it("calls getJson with /jobs and content_type=job by default", async () => {
      vi.mocked(getJson).mockResolvedValueOnce([mockJob]);

      const result = await opportunityService.list();

      expect(getJson).toHaveBeenCalledWith("/jobs", { content_type: "job" });
      expect(result).toEqual([mockJob]);
    });

    it("passes content_type from params", async () => {
      vi.mocked(getJson).mockResolvedValueOnce([]);

      await opportunityService.list({ content_type: "internship" });

      expect(getJson).toHaveBeenCalledWith("/jobs", { content_type: "internship" });
    });

    it("handles numeric param as workspace_id", async () => {
      vi.mocked(getJson).mockResolvedValueOnce([]);

      await opportunityService.list(42);

      expect(getJson).toHaveBeenCalledWith("/jobs", { workspace_id: 42, content_type: "job" });
    });
  });

  describe("detail", () => {
    it("calls getJson with /jobs/:id", async () => {
      vi.mocked(getJson).mockResolvedValueOnce(mockJob);

      const result = await opportunityService.detail(1);

      expect(getJson).toHaveBeenCalledWith("/jobs/1", undefined);
      expect(result).toEqual(mockJob);
    });

    it("passes workspace_id when provided", async () => {
      vi.mocked(getJson).mockResolvedValueOnce(mockJob);

      await opportunityService.detail(1, 42);

      expect(getJson).toHaveBeenCalledWith("/jobs/1", { workspace_id: 42 });
    });
  });

  describe("create", () => {
    it("posts to /jobs with the payload", async () => {
      const payload = { title: "New Job", description: "Desc", source: "Manual" };
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: mockJob });

      const result = await opportunityService.create(payload);

      expect(apiClient.post).toHaveBeenCalledWith("/jobs", payload);
      expect(result).toEqual(mockJob);
    });
  });

  describe("remove", () => {
    it("deletes /jobs/:id", async () => {
      vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: { status: "deleted" } });

      const result = await opportunityService.remove(1);

      expect(apiClient.delete).toHaveBeenCalledWith("/jobs/1", { params: { workspace_id: undefined } });
      expect(result).toEqual({ status: "deleted" });
    });
  });

  describe("score", () => {
    it("posts to /jobs/:id/score", async () => {
      const scoreResult = { classification: "job", match_score: 90 };
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: scoreResult });

      const result = await opportunityService.score(1);

      expect(apiClient.post).toHaveBeenCalledWith("/jobs/1/score", null, { params: {} });
      expect(result).toEqual(scoreResult);
    });

    it("passes profile_id when provided", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: {} });

      await opportunityService.score(1, 5);

      expect(apiClient.post).toHaveBeenCalledWith("/jobs/1/score", null, { params: { profile_id: 5 } });
    });
  });

  describe("scoreBatch", () => {
    it("posts to /jobs/score-batch", async () => {
      const batchResult: BatchScoreResult = {
        status: "ok", total: 2, succeeded: 2, skipped: 0, failed: 0,
        results: [{ job_id: 1, status: "success" }],
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: batchResult });

      const result = await opportunityService.scoreBatch({ job_ids: [1, 2] });

      expect(apiClient.post).toHaveBeenCalledWith("/jobs/score-batch", { job_ids: [1, 2], score_all_unscored: undefined, profile_id: undefined });
      expect(result).toEqual(batchResult);
    });
  });

  describe("scoreFeedback", () => {
    it("posts feedback as relevant", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { status: "ok" } });

      await opportunityService.scoreFeedback(1, "relevant");

      expect(apiClient.post).toHaveBeenCalledWith("/jobs/1/score-feedback", { signal: "relevant" });
    });
  });

  describe("materials", () => {
    it("calls getJson for job materials", async () => {
      vi.mocked(getJson).mockResolvedValueOnce({ cover_letter: "draft" });

      const result = await opportunityService.materials(1);

      expect(getJson).toHaveBeenCalledWith("/jobs/1/materials");
      expect(result).toEqual({ cover_letter: "draft" });
    });
  });

  describe("updateStatus", () => {
    it("patches job status", async () => {
      vi.mocked(apiClient.patch).mockResolvedValueOnce({ data: { status: "applied" } });

      await opportunityService.updateStatus(1, "applied", "some notes");

      expect(apiClient.patch).toHaveBeenCalledWith("/jobs/1/status", undefined, { params: { status: "applied", notes: "some notes" } });
    });
  });

  describe("reminders", () => {
    it("calls getJson for reminders", async () => {
      const reminders: Reminder[] = [{ id: 1, title: "Follow up", due_at: "2026-07-01", status: "pending" }];
      vi.mocked(getJson).mockResolvedValueOnce(reminders);

      const result = await opportunityService.reminders();

      expect(getJson).toHaveBeenCalledWith("/reminders");
      expect(result).toEqual(reminders);
    });
  });

  describe("gmailStatus", () => {
    it("calls getJson for gmail status", async () => {
      vi.mocked(getJson).mockResolvedValueOnce({ connected: true, status: "ok", connected_email: "a@b.com" });

      const result = await opportunityService.gmailStatus();

      expect(getJson).toHaveBeenCalledWith("/gmail/status");
      expect(result.connected).toBe(true);
    });
  });

  describe("linkedinStatus", () => {
    it("calls getJson for linkedin status", async () => {
      vi.mocked(getJson).mockResolvedValueOnce({ connected: true, configured: true, status: "ok" });

      const result = await opportunityService.linkedinStatus();

      expect(getJson).toHaveBeenCalledWith("/linkedin/status");
      expect(result.connected).toBe(true);
    });
  });

  describe("profiles", () => {
    it("calls getJson for profiles", async () => {
      const profiles: Profile[] = [{ id: 1, name: "Default", is_default: 1 }];
      vi.mocked(getJson).mockResolvedValueOnce(profiles);

      const result = await opportunityService.profiles();

      expect(getJson).toHaveBeenCalledWith("/profiles");
      expect(result).toEqual(profiles);
    });
  });

  describe("linkedinSearchJobs", () => {
    it("posts to linkedin search", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { status: "ok", opportunities: [mockJob], raw_count: 1 } });

      const result = await opportunityService.linkedinSearchJobs({ title_filter: "engineer", location_filter: "US" });

      expect(apiClient.post).toHaveBeenCalledWith("/linkedin/jobs/search", { title_filter: "engineer", location_filter: "US", offset: undefined, count: undefined, workspace_id: undefined });
      expect(result.opportunities).toHaveLength(1);
    });
  });

  describe("discoverPublic", () => {
    it("posts to /discovery/public", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { status: "ok", opportunities: [mockJob] } });

      const result = await opportunityService.discoverPublic({
        query: "engineer", sources: ["RemoteOk"], limit_per_source: 10,
        opportunity_type: "job", remote_type: "remote", location: "US", keywords: "react",
      });

      expect(apiClient.post).toHaveBeenCalledWith("/discovery/public", {
        query: "engineer", sources: ["RemoteOk"], limit_per_source: 10,
        opportunity_type: "job", remote_type: "remote", location: "US", keywords: "react",
        country: undefined, max_age_days: undefined,
      });
      expect(result.opportunities).toHaveLength(1);
    });
  });

  describe("manualEntry", () => {
    it("posts to /discovery/manual-entry", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { status: "ok", id: 1, ids: [1], imported: 1, skipped_duplicates: 0 } });

      const result = await opportunityService.manualEntry({
        title: "Dev", company: "Co", description: "desc",
      });

      expect(apiClient.post).toHaveBeenCalledWith("/discovery/manual-entry", {
        title: "Dev", company: "Co", description: "desc",
        url: undefined, location: undefined, remote_type: undefined,
        salary_min: undefined, salary_max: undefined, deadline: undefined,
        opportunity_type: undefined, source: undefined, workspace_id: undefined,
      });
      expect(result.imported).toBe(1);
    });
  });
});
