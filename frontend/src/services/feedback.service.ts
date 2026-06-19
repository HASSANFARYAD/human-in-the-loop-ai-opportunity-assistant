import { apiClient, getJson } from "@/services/client";
import type { Feedback } from "@/types/api";

export const feedbackService = {
  list: (workspace_id?: number, limit = 100) => getJson<Feedback[]>("/feedback", { workspace_id, limit }),
  create: async (payload: Omit<Feedback, "id"> & Record<string, unknown>) => (await apiClient.post("/feedback", payload)).data,
  updateStatus: async (id: number, status: string) => (await apiClient.patch(`/feedback/${id}/status`, { status })).data,
};
