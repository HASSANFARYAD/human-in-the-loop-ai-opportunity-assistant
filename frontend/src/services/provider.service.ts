import { apiClient, getJson } from "@/services/client";
import type { Integration, ProviderConfig } from "@/types/api";

export const providerService = {
  integrations: (workspace_id?: number) => getJson<Integration[]>("/integrations", { workspace_id }),
  saveIntegration: async (service: string, payload: Record<string, unknown>) => (await apiClient.put(`/integrations/${service}`, payload)).data,
  providers: (platform?: string, workspace_id?: number) => getJson<ProviderConfig[]>("/providers", { platform, workspace_id }),
  health: (platform?: string, workspace_id?: number) => getJson<Record<string, unknown>>("/providers/health", { platform, workspace_id }),
  aiHealth: () => getJson<Record<string, unknown>>("/health/ai"),
  generations: (workspace_id?: number, limit = 100) => getJson<unknown[]>("/ai/generations", { workspace_id, limit }),
  prompts: () => getJson<unknown[]>("/ai/prompts"),
};
