import { apiClient, getJson } from "@/services/client";
import type { Integration, ProviderConfig } from "@/types/api";

export const providerService = {
  integrations: (workspace_id?: number) => getJson<Integration[]>("/integrations", { workspace_id }),
  saveIntegration: async (service: string, payload: Record<string, unknown>) => (await apiClient.put(`/integrations/${service}`, payload)).data,
  deleteIntegration: async (service: string, workspace_id?: number) => (await apiClient.delete(`/integrations/${service}`, { params: { workspace_id } })).data,
  providers: (platform?: string, workspace_id?: number) => getJson<ProviderConfig[]>("/providers", { platform, workspace_id }),
  saveProvider: async (payload: Record<string, unknown>) => (await apiClient.post("/providers", payload)).data,
  deleteProvider: async (platform: string, providerName: string, workspace_id?: number) =>
    (await apiClient.delete(`/providers/${platform}/${providerName}`, { params: { workspace_id } })).data,
  health: (platform?: string, workspace_id?: number) => getJson<Record<string, unknown>>("/providers/health", { platform, workspace_id }),
  aiHealth: () => getJson<Record<string, unknown>>("/health/ai"),
  generations: (workspace_id?: number, limit = 100) => getJson<unknown[]>("/ai/generations", { workspace_id, limit }),
  prompts: () => getJson<unknown[]>("/ai/prompts"),
};
