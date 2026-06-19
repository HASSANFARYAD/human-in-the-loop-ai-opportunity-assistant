import { apiClient, getJson } from "@/services/client";
import type { AutomationRule, AutomationRun } from "@/types/api";

export const automationService = {
  rules: (workspace_id?: number) => getJson<AutomationRule[]>("/automation/rules", { workspace_id }),
  runs: (workspace_id?: number, limit = 100) => getJson<AutomationRun[]>("/automation/runs", { workspace_id, limit }),
  errors: (workspace_id?: number, limit = 100) => getJson<AutomationRun[]>("/automation/errors", { workspace_id, limit }),
  createRule: async (payload: Partial<AutomationRule> & Record<string, unknown>) => (await apiClient.post("/automation/rules", payload)).data,
  updateRule: async (id: number, payload: Partial<AutomationRule> & Record<string, unknown>) =>
    (await apiClient.put(`/automation/rules/${id}`, payload)).data,
  deleteRule: async (id: number, workspace_id?: number) => (await apiClient.delete(`/automation/rules/${id}`, { params: { workspace_id } })).data,
  trigger: async (trigger_event: string, payload: Record<string, unknown> = {}, workspace_id?: number) =>
    (await apiClient.post("/automation/trigger", { trigger_event, payload, workspace_id })).data,
};
