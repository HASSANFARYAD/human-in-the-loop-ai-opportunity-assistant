import { API_ORIGIN, apiClient, ensureAccessToken } from "@/services/client";
import type { AgentChatResponse, AgentSection } from "@/types/api";

export interface AgentChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface AgentStreamHandlers {
  onIntents?: (intents: string[]) => void;
  onSection?: (section: AgentSection) => void;
  onDelta?: (text: string) => void;
  onError?: (message: string) => void;
}

export const agentService = {
  chat: async (message: string, history: AgentChatTurn[] = [], workspace_id?: number) =>
    (await apiClient.post<AgentChatResponse>("/agent/chat", { message, history, workspace_id })).data,

  chatStream: async (
    message: string,
    history: AgentChatTurn[],
    handlers: AgentStreamHandlers,
    workspace_id?: number,
    signal?: AbortSignal,
  ) => {
    const token = await ensureAccessToken();
    const res = await fetch(`${API_ORIGIN}/agent/chat/stream`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ message, history, workspace_id }),
      signal,
    });
    if (!res.ok || !res.body) {
      handlers.onError?.(`Request failed (${res.status})`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const dispatch = (block: string) => {
      let event = "";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (!event) return;
      try {
        const parsed = data ? JSON.parse(data) : {};
        if (event === "intents") handlers.onIntents?.(parsed.intents ?? []);
        else if (event === "section") handlers.onSection?.(parsed as AgentSection);
        else if (event === "delta") handlers.onDelta?.(parsed.text ?? "");
        else if (event === "error") handlers.onError?.(parsed.message ?? "Stream error");
      } catch {
        handlers.onError?.("Failed to parse stream data");
      }
    };

    for (;;) {
      if (signal?.aborted) break;
      let result;
      try {
        result = await reader.read();
      } catch {
        break;
      }
      const { done, value } = result;
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        if (block.trim()) dispatch(block);
      }
    }
    if (buffer.trim()) dispatch(buffer);
  },
};
