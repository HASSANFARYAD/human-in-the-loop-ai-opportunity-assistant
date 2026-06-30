import { apiClient, getJson } from "@/services/client";
import type { Loop, LoopRun, LoopStatus, AutoApplyLog, AutoApplyStats, AutoApplyHealth } from "@/types/api";

export const loopsService = {
  list: (includeInactive = false, workspaceId?: number) =>
    getJson<Loop[]>("/loops", { include_inactive: includeInactive, workspace_id: workspaceId }),
  get: (id: number, workspaceId?: number) => getJson<Loop>(`/loops/${id}`, { workspace_id: workspaceId }),
  create: async (payload: Partial<Loop> & Record<string, unknown>) => (await apiClient.post("/loops", payload)).data,
  update: async (id: number, payload: Partial<Loop> & Record<string, unknown>) =>
    (await apiClient.put(`/loops/${id}`, payload)).data,
  delete: async (id: number, workspaceId?: number) =>
    (await apiClient.delete(`/loops/${id}`, { params: { workspace_id: workspaceId } })).data,
  run: async (id: number, workspaceId?: number) =>
    (await apiClient.post(`/loops/${id}/run`, { workspace_id: workspaceId })).data,
  status: (id: number, workspaceId?: number) => getJson<LoopStatus>(`/loops/${id}/status`, { workspace_id: workspaceId }),
  runs: (id: number, limit = 50, workspaceId?: number) =>
    getJson<LoopRun[]>(`/loops/${id}/runs`, { limit, workspace_id: workspaceId }),
  autoApplyLogs: (limit = 100, status?: string, loopId?: number, workspaceId?: number) =>
    getJson<AutoApplyLog[]>("/auto-apply/logs", { limit, status, loop_id: loopId, workspace_id: workspaceId }),
  autoApplyStats: (days = 30, workspaceId?: number) =>
    getJson<AutoApplyStats>("/auto-apply/stats", { days, workspace_id: workspaceId }),
  dailyApplyCount: (workspaceId?: number) =>
    getJson<{ count: number }>("/auto-apply/daily-count", { workspace_id: workspaceId }),
  pendingApproval: (limit = 50, workspaceId?: number) =>
    getJson<AutoApplyLog[]>("/auto-apply/pending-approval", { limit, workspace_id: workspaceId }),
  health: () => getJson<AutoApplyHealth>("/auto-apply/health"),
  resetCircuitBreaker: async (source?: string) =>
    (await apiClient.post("/auto-apply/health/reset-circuit-breaker", {}, { params: { source } })).data,
};
