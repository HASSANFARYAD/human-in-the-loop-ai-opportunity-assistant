import { describe, it, expect, vi, beforeEach } from "vitest";
import type { AgentChatResponse, Conversation, ConversationDetail, AgentPersona, AgentMemory, PromptVersion } from "@/types/api";

vi.mock("@/services/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  ensureAccessToken: vi.fn(),
  API_ORIGIN: "http://localhost:8001/api/v1",
}));

import { agentService, type AgentStreamHandlers } from "@/services/agent.service";
import { apiClient, ensureAccessToken } from "@/services/client";

const mockConversation: Conversation = {
  id: 1,
  conversation_id: 1,
  user_id: 1,
  title: "Test Chat",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const mockPersona: AgentPersona = { tone: "professional", detail_level: "balanced", focus_area: "general" };

describe("agentService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("chat", () => {
    it("posts to /agent/chat with message and history", async () => {
      const response: AgentChatResponse = { intents: ["greeting"], sections: [] };
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: response });

      const result = await agentService.chat("Hello", [{ role: "user", content: "Hi" }]);

      expect(apiClient.post).toHaveBeenCalledWith("/agent/chat", {
        message: "Hello", history: [{ role: "user", content: "Hi" }], workspace_id: undefined,
      });
      expect(result).toEqual(response);
    });

    it("passes workspace_id when provided", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { intents: [], sections: [] } });

      await agentService.chat("Hello", [], 42);

      expect(apiClient.post).toHaveBeenCalledWith("/agent/chat", {
        message: "Hello", history: [], workspace_id: 42,
      });
    });
  });

  describe("chatStream", () => {
    let mockReader: ReadableStreamDefaultReader;
    let mockFetch: ReturnType<typeof vi.fn>;

    beforeEach(() => {
      vi.mocked(ensureAccessToken).mockResolvedValue("test-token");

      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode("event: conversation\ndata: {\"conversation_id\":1}\n\n"));
          controller.enqueue(encoder.encode("event: intents\ndata: {\"intents\":[\"job_search\"]}\n\n"));
          controller.enqueue(encoder.encode("event: section\ndata: {\"agent\":\"job_search\",\"type\":\"message\",\"message\":\"Hello!\"}\n\n"));
          controller.enqueue(encoder.encode("event: suggestions\ndata: {\"suggestions\":[\"Find jobs\"]}\n\n"));
          controller.enqueue(encoder.encode("event: done\ndata: {\"conversation_id\":1,\"message_id\":42}\n\n"));
          controller.close();
        },
      });

      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        body: stream,
      });
      vi.stubGlobal("fetch", mockFetch);
    });

    it("sends SSE request and calls handlers", async () => {
      const handlers: AgentStreamHandlers = {
        onConversation: vi.fn(),
        onIntents: vi.fn(),
        onSection: vi.fn(),
        onDelta: vi.fn(),
        onSuggestions: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      };

      await agentService.chatStream("Hello", [], handlers);

      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8001/api/v1/agent/chat/stream",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ message: "Hello", history: [], conversation_id: undefined, workspace_id: undefined }),
        }),
      );
      expect(handlers.onConversation).toHaveBeenCalledWith(1);
      expect(handlers.onIntents).toHaveBeenCalledWith(["job_search"]);
      expect(handlers.onSection).toHaveBeenCalledWith({ agent: "job_search", type: "message", message: "Hello!" });
      expect(handlers.onSuggestions).toHaveBeenCalledWith(["Find jobs"]);
      expect(handlers.onDone).toHaveBeenCalledWith({ conversation_id: 1, message_id: 42 });
    });

    it("calls onError when response fails", async () => {
      mockFetch.mockResolvedValueOnce({ ok: false, status: 500 });
      const onError = vi.fn();

      await agentService.chatStream("Hello", [], { onError });

      expect(onError).toHaveBeenCalledWith("Request failed (500)");
    });

    it("calls onError on empty response body", async () => {
      mockFetch.mockResolvedValueOnce({ ok: true });
      const onError = vi.fn();

      await agentService.chatStream("Hello", [], { onError });

      expect(onError).toHaveBeenCalledWith("Request failed (undefined)");
    });
  });

  describe("listConversations", () => {
    it("calls get for conversations", async () => {
      vi.mocked(apiClient.get).mockResolvedValueOnce({ data: [mockConversation] });

      const result = await agentService.listConversations();

      expect(apiClient.get).toHaveBeenCalledWith("/agent/conversations");
      expect(result).toEqual([mockConversation]);
    });
  });

  describe("getConversation", () => {
    it("calls get for conversation detail", async () => {
      const detail: ConversationDetail = { ...mockConversation, messages: [] };
      vi.mocked(apiClient.get).mockResolvedValueOnce({ data: detail });

      const result = await agentService.getConversation(1);

      expect(apiClient.get).toHaveBeenCalledWith("/agent/conversations/1");
      expect(result).toEqual(detail);
    });
  });

  describe("createConversation", () => {
    it("posts to create conversation", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { conversation_id: 1, title: "New Chat" } });

      const result = await agentService.createConversation("New Chat");

      expect(apiClient.post).toHaveBeenCalledWith("/agent/conversations", { title: "New Chat", workspace_id: undefined });
      expect(result).toEqual({ conversation_id: 1, title: "New Chat" });
    });
  });

  describe("deleteConversation", () => {
    it("deletes conversation", async () => {
      vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: { status: "deleted" } });

      await agentService.deleteConversation(1);

      expect(apiClient.delete).toHaveBeenCalledWith("/agent/conversations/1");
    });
  });

  describe("recordFeedback", () => {
    it("posts feedback for a message", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { status: "ok" } });

      await agentService.recordFeedback(1, 42, "thumbs_up");

      expect(apiClient.post).toHaveBeenCalledWith("/agent/conversations/1/feedback", { message_id: 42, rating: "thumbs_up" });
    });
  });

  describe("getPersona", () => {
    it("calls get for persona", async () => {
      vi.mocked(apiClient.get).mockResolvedValueOnce({ data: { persona: mockPersona } });

      const result = await agentService.getPersona();

      expect(apiClient.get).toHaveBeenCalledWith("/agent/persona");
      expect(result).toEqual(mockPersona);
    });
  });

  describe("updatePersona", () => {
    it("puts persona", async () => {
      vi.mocked(apiClient.put).mockResolvedValueOnce({ data: { status: "ok" } });

      await agentService.updatePersona(mockPersona);

      expect(apiClient.put).toHaveBeenCalledWith("/agent/persona", mockPersona);
    });
  });

  describe("listPrompts", () => {
    it("calls get for prompts", async () => {
      const prompts: PromptVersion[] = [{ id: 1, name: "scoring", version: "1.0", template: "..." }];
      vi.mocked(apiClient.get).mockResolvedValueOnce({ data: prompts });

      const result = await agentService.listPrompts();

      expect(apiClient.get).toHaveBeenCalledWith("/admin/prompts");
      expect(result).toEqual(prompts);
    });
  });

  describe("listMemories", () => {
    it("calls get for memories", async () => {
      const memories: AgentMemory[] = [{ id: 1, key: "skill", value: "React", source: "manual", created_at: "", updated_at: "" }];
      vi.mocked(apiClient.get).mockResolvedValueOnce({ data: memories });

      const result = await agentService.listMemories();

      expect(apiClient.get).toHaveBeenCalledWith("/agent/memories");
      expect(result).toEqual(memories);
    });
  });

  describe("createMemory", () => {
    it("posts to create memory", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { id: 1, status: "created" } });

      const result = await agentService.createMemory("key", "value");

      expect(apiClient.post).toHaveBeenCalledWith("/agent/memories", { key: "key", value: "value" });
      expect(result).toEqual({ id: 1, status: "created" });
    });
  });
});
