import { apiClient } from "@/services/client";
import type { AgentChatResponse } from "@/types/api";

export interface AgentChatTurn {
  role: "user" | "assistant";
  content: string;
}

export const agentService = {
  chat: async (message: string, history: AgentChatTurn[] = [], workspace_id?: number) =>
    (await apiClient.post<AgentChatResponse>("/agent/chat", { message, history, workspace_id })).data,
};
