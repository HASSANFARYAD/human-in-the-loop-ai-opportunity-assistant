import { apiClient, getJson } from "@/services/client";
import type { BatchScoreResult, Opportunity, OpportunityContentType, Profile, ProfileJobDiscoveryResult, TailoredResume } from "@/types/api";

export interface OpportunityCreate {
  workspace_id?: number;
  title: string;
  company?: string;
  location?: string;
  remote_type?: string;
  url?: string;
  source: string;
  description: string;
  salary_min?: number;
  salary_max?: number;
  deadline?: string;
  opportunity_type?: string;
  classification?: string;
  classification_reason?: string;
  classification_confidence?: number;
  opportunity_confidence?: number;
  importable?: boolean;
  blocked_reason?: string;
}

export interface OpportunityListParams {
  workspace_id?: number;
  content_type?: OpportunityContentType;
}

export const opportunityService = {
  list: (params?: OpportunityListParams | number) => {
    const requestParams = typeof params === "number" ? { workspace_id: params, content_type: "job" } : { content_type: "job", ...(params ?? {}) };
    return getJson<Opportunity[]>("/jobs", requestParams);
  },
  detail: (id: number, workspace_id?: number) => getJson<Opportunity>(`/jobs/${id}`, workspace_id ? { workspace_id } : undefined),
  create: async (payload: OpportunityCreate) => (await apiClient.post("/jobs", payload)).data,
  remove: async (id: number, workspace_id?: number) => (await apiClient.delete(`/jobs/${id}`, { params: { workspace_id } })).data,
  score: async (id: number) => (await apiClient.post(`/jobs/${id}/score`)).data,
  scoreBatch: async (payload: { job_ids: number[]; score_all_unscored?: boolean }) =>
    (await apiClient.post<BatchScoreResult>("/jobs/score-batch", payload)).data,
  materials: (id: number) => getJson<Record<string, unknown>>(`/jobs/${id}/materials`),
  generateMaterials: async (id: number) => (await apiClient.post(`/jobs/${id}/generate-materials`)).data,
  tailorResume: async (id: number) => (await apiClient.post<TailoredResume>(`/jobs/${id}/tailor-resume`)).data,
  resumeReview: async (id: number, payload: { resume_text?: string; target_role?: string } = {}) =>
    (await apiClient.post<Record<string, unknown>>(`/jobs/${id}/resume-review`, payload)).data,
  resumeReviews: (id: number) => getJson<TailoredResume[]>("/profile/resume-reviews", { job_id: id }),
  interviewPrep: async (id: number) => (await apiClient.post<Record<string, unknown>>(`/jobs/${id}/interview-prep`)).data,
  interviewPrepSessions: (id: number) => getJson<Record<string, unknown>[]>(`/jobs/${id}/interview-prep`),
  recordings: (id?: number) => getJson<Record<string, unknown>[]>("/recordings", id ? { job_id: id } : undefined),
  saveRecording: async (payload: { job_id?: number; title: string; mime_type: string; data_url: string; duration_ms?: number }) =>
    (await apiClient.post<Record<string, unknown>>("/recordings", payload)).data,
  uploadRecording: async (payload: { job_id?: number; title: string; blob: Blob; duration_ms?: number }) => {
    const form = new FormData();
    if (payload.job_id) form.append("job_id", String(payload.job_id));
    form.append("title", payload.title);
    form.append("duration_ms", String(payload.duration_ms ?? 0));
    form.append("file", payload.blob, "recording.webm");
    return (await apiClient.post<Record<string, unknown>>("/recordings/upload", form)).data;
  },
  profile: () => getJson<Profile>("/profile"),
  updateProfile: async (payload: Profile) => (await apiClient.post("/profile", payload)).data,
  gmailStatus: () => getJson<{ connected: boolean; configured?: boolean; status: string; connected_email?: string }>("/gmail/status"),
  gmailAuthUrl: async () => (await apiClient.get<{ url: string }>("/gmail/auth-url")).data,
  gmailDisconnect: async () => (await apiClient.post("/gmail/disconnect")).data,
  gmailMessages: () => getJson<Record<string, unknown>[]>("/gmail/messages"),
  updateStatus: async (id: number, status: string, notes = "") =>
    (await apiClient.patch(`/jobs/${id}/status`, undefined, { params: { status, notes } })).data,
  reminders: () => getJson<unknown[]>("/reminders"),
  extract: async (payload: { raw: string; source: string; opportunity_type: string; work_location_filter?: string; workspace_id?: number }) =>
    (await apiClient.post<{ status: string; opportunity?: Opportunity; opportunities?: Opportunity[]; raw_count?: number; work_location_filter?: string; jobs_found?: number; jobs_skipped_location_filter?: number; warnings?: string[]; message?: string }>("/discovery/extract", payload)).data,
  discoverPublic: async (payload: {
    query: string;
    sources: string[];
    limit_per_source: number;
    opportunity_type: string;
    remote_type: string;
    location: string;
    keywords: string;
    country?: string;
  }) => (await apiClient.post<{ status: string; opportunities: Opportunity[] }>("/discovery/public", payload)).data,
  discoverFromProfile: async (payload: { sources?: string[]; limit_per_source?: number; save_results?: boolean; score_results?: boolean } = {}) =>
    (await apiClient.post<ProfileJobDiscoveryResult>("/discovery/from-profile", payload)).data,
  discoverRapidApiLinkedIn: async (payload: { title_filter: string; location_filter: string; offset: number; workspace_id?: number }) =>
    (await apiClient.post<{ status: string; opportunities: Opportunity[]; raw_count: number }>("/discovery/rapidapi-linkedin", payload)).data,
  discoverApify: async (payload: { url: string; workspace_id?: number }) =>
    (await apiClient.post<{ status: string; opportunities: Opportunity[]; raw_count: number }>("/discovery/apify", payload)).data,
  importUrl: async (payload: { url: string; source: string; work_location_filter?: string; page_limit?: number; workspace_id?: number }) =>
    (await apiClient.post<{ status: string; source: string; work_location_filter?: string; jobs_found?: number; jobs_imported?: number; jobs_skipped_duplicates?: number; jobs_skipped_location_filter?: number; found: number; imported: number; skipped_duplicates: number; errors: string[]; warnings: string[]; ids: number[] }>("/discovery/import-url", payload)).data,
  importDiscovered: async (opportunities: Opportunity[], workspace_id?: number) =>
    (await apiClient.post<{ status: string; ids: number[]; count: number; found?: number; imported?: number; skipped_duplicates?: number; errors?: string[]; warnings?: string[] }>("/discovery/import", { opportunities, workspace_id })).data,
};
