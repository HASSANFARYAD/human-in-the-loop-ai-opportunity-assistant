import { apiClient, getJson } from "@/services/client";
import type { Workspace } from "@/types/api";

export const workspaceService = {
  bootstrap: () => getJson<{ workspace: Workspace; summary: Record<string, unknown> }>("/enterprise/bootstrap"),
  list: () => getJson<Workspace[]>("/workspaces"),
  summary: () => getJson<Record<string, unknown>>("/enterprise/summary"),
  members: (workspaceId: number) => getJson<unknown[]>(`/workspaces/${workspaceId}/members`),
  createOrganization: async (name: string) => (await apiClient.post("/organizations", { name })).data,
  createWorkspace: async (payload: { organization_id: number; name: string; description?: string }) =>
    (await apiClient.post("/workspaces", payload)).data,
  addMember: async (workspaceId: number, payload: { email: string; role: string }) =>
    (await apiClient.post(`/workspaces/${workspaceId}/members`, payload)).data,
  roles: () => getJson<unknown[]>("/roles"),
  permissions: () => getJson<Record<string, unknown>>("/permissions"),
};
