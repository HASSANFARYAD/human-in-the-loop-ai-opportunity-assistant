import { API_ORIGIN, apiClient, ensureAccessToken } from "@/services/client";
import type { AgentChatResponse, AgentMemory, AgentPersona, AgentSection, Conversation, ConversationDetail, PromptVersion } from "@/types/api";

export interface AgentChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface AgentStreamHandlers {
  onConversation?: (conversation_id: number) => void;
  onIntents?: (intents: string[]) => void;
  onSection?: (section: AgentSection) => void;
  onDelta?: (text: string) => void;
  onSuggestions?: (suggestions: string[]) => void;
  onDone?: (data: { conversation_id: number; message_id?: number }) => void;
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
    conversation_id?: number,
    signal?: AbortSignal,
  ) => {
    const token = await ensureAccessToken();
    const res = await fetch(`${API_ORIGIN}/agent/chat/stream`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ message, history, conversation_id, workspace_id }),
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
        if (event === "conversation") handlers.onConversation?.(parsed.conversation_id);
        else if (event === "intents") handlers.onIntents?.(parsed.intents ?? []);
        else if (event === "section") handlers.onSection?.(parsed as AgentSection);
        else if (event === "delta") handlers.onDelta?.(parsed.text ?? "");
        else if (event === "suggestions") handlers.onSuggestions?.(parsed.suggestions ?? []);
        else if (event === "done") handlers.onDone?.(parsed);
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

  listConversations: async () =>
    (await apiClient.get<Conversation[]>("/agent/conversations")).data,

  getConversation: async (id: number) =>
    (await apiClient.get<ConversationDetail>(`/agent/conversations/${id}`)).data,

  createConversation: async (title: string, workspace_id?: number) =>
    (await apiClient.post<{ conversation_id: number; title: string }>("/agent/conversations", { title, workspace_id })).data,

  updateConversation: async (id: number, title: string) =>
    (await apiClient.patch(`/agent/conversations/${id}`, { title })).data,

  deleteConversation: async (id: number) =>
    (await apiClient.delete(`/agent/conversations/${id}`)).data,

  recordFeedback: async (conversation_id: number, message_id: number, rating: "thumbs_up" | "thumbs_down") =>
    (await apiClient.post(`/agent/conversations/${conversation_id}/feedback`, { message_id, rating })).data,

  getPersona: async () =>
    (await apiClient.get<{ persona: AgentPersona }>("/agent/persona")).data.persona,

  updatePersona: async (persona: AgentPersona) =>
    (await apiClient.put("/agent/persona", persona)).data,

  listPrompts: async () =>
    (await apiClient.get<PromptVersion[]>("/admin/prompts")).data,

  upsertPrompt: async (prompt: PromptVersion) =>
    (await apiClient.post("/admin/prompts", prompt)).data,

  deletePrompt: async (name: string, version: string) =>
    (await apiClient.delete(`/admin/prompts?name=${encodeURIComponent(name)}&version=${encodeURIComponent(version)}`)).data,

  listMemories: async () =>
    (await apiClient.get<AgentMemory[]>("/agent/memories")).data,

  createMemory: async (key: string, value: string) =>
    (await apiClient.post<{ id: number; status: string }>("/agent/memories", { key, value })).data,

  updateMemory: async (id: number, key: string, value: string) =>
    (await apiClient.put(`/agent/memories/${id}`, { key, value })).data,

  deleteMemory: async (id: number) =>
    (await apiClient.delete(`/agent/memories/${id}`)).data,
};
