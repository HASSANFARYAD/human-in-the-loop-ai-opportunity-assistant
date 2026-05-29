import { apiClient, getJson } from "@/services/client";
import type { Opportunity } from "@/types/api";

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
}

export const opportunityService = {
  list: (workspace_id?: number) => getJson<Opportunity[]>("/jobs", workspace_id ? { workspace_id } : undefined),
  detail: (id: number, workspace_id?: number) => getJson<Opportunity>(`/jobs/${id}`, workspace_id ? { workspace_id } : undefined),
  create: async (payload: OpportunityCreate) => (await apiClient.post("/jobs", payload)).data,
  remove: async (id: number, workspace_id?: number) => (await apiClient.delete(`/jobs/${id}`, { params: { workspace_id } })).data,
  score: async (id: number) => (await apiClient.post(`/jobs/${id}/score`)).data,
  materials: (id: number) => getJson<Record<string, unknown>>(`/jobs/${id}/materials`),
  generateMaterials: async (id: number) => (await apiClient.post(`/jobs/${id}/generate-materials`)).data,
  updateStatus: async (id: number, status: string, notes = "") =>
    (await apiClient.patch(`/jobs/${id}/status`, undefined, { params: { status, notes } })).data,
  reminders: () => getJson<unknown[]>("/reminders"),
  extract: async (payload: { raw: string; source: string; opportunity_type: string; workspace_id?: number }) =>
    (await apiClient.post<{ status: string; opportunity: Opportunity }>("/discovery/extract", payload)).data,
  discoverPublic: async (payload: {
    query: string;
    sources: string[];
    limit_per_source: number;
    opportunity_type: string;
    remote_type: string;
    location: string;
    keywords: string;
  }) => (await apiClient.post<{ status: string; opportunities: Opportunity[] }>("/discovery/public", payload)).data,
  discoverRapidApiLinkedIn: async (payload: { title_filter: string; location_filter: string; offset: number; workspace_id?: number }) =>
    (await apiClient.post<{ status: string; opportunities: Opportunity[]; raw_count: number }>("/discovery/rapidapi-linkedin", payload)).data,
  discoverApify: async (payload: { url: string; workspace_id?: number }) =>
    (await apiClient.post<{ status: string; opportunities: Opportunity[]; raw_count: number }>("/discovery/apify", payload)).data,
  importDiscovered: async (opportunities: Opportunity[], workspace_id?: number) =>
    (await apiClient.post<{ status: string; ids: number[]; count: number }>("/discovery/import", { opportunities, workspace_id })).data,
};
