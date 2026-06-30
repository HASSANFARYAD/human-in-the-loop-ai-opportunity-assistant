import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Conversation, ConversationDetail, AgentSection } from "@/types/api";

const mockActiveWorkspace = { id: 1, name: "Test Workspace" };
vi.mock("@/stores/auth-store", () => ({
  useAuthStore: (selector: any) =>
    selector({ activeWorkspace: mockActiveWorkspace }),
}));

const mockConversations: Conversation[] = [
  { id: 1, conversation_id: 1, user_id: 1, title: "Chat 1", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
  { id: 2, conversation_id: 2, user_id: 1, title: "Chat 2", created_at: "2026-01-02T00:00:00Z", updated_at: "2026-01-02T00:00:00Z" },
];

const mockConversationDetail: ConversationDetail = {
  ...mockConversations[0],
  messages: [
    { id: 1, conversation_id: 1, role: "user", content: "Hello", sections: [], created_at: "2026-01-01T00:00:00Z" },
    { id: 2, conversation_id: 1, role: "assistant", content: "Hi there!", sections: [{ agent: "chat", type: "message", message: "Hi there!" }], created_at: "2026-01-01T00:00:00Z" },
  ],
};

const mockQueries: Record<string, any> = {};
let mockMutateFn: any = null;
let mockMutateOnSuccess: any = null;

vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryKey }: { queryKey: string[] }) => {
    const key = queryKey[0];
    return mockQueries[key] ?? { data: undefined, isLoading: false };
  },
  useMutation: ({ mutationFn, onSuccess }: any) => {
    mockMutateFn = mutationFn;
    mockMutateOnSuccess = onSuccess;
    return {
      mutate: async (...args: any[]) => {
        try {
          const data = await mutationFn(...args);
          onSuccess?.(data);
        } catch {}
      },
      isPending: false,
    };
  },
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/services/agent.service", () => ({
  agentService: {
    listConversations: vi.fn(),
    getConversation: vi.fn(),
    deleteConversation: vi.fn(),
    chatStream: vi.fn(),
    recordFeedback: vi.fn(),
  },
}));

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
    button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

import { AgentChatView } from "@/features/agent/agent-chat-view";
import { agentService } from "@/services/agent.service";

describe("AgentChatView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockQueries["conversations"] = { data: mockConversations };
  });

  it("renders title and description", () => {
    render(<AgentChatView />);
    expect(screen.getByText("Career Assistant")).toBeTruthy();
    expect(screen.getByText(/Ask in plain language/)).toBeTruthy();
  });

  it("renders conversation sidebar", () => {
    render(<AgentChatView />);
    expect(screen.getByText("Conversations")).toBeTruthy();
    expect(screen.getByText("Chat 1")).toBeTruthy();
    expect(screen.getByText("Chat 2")).toBeTruthy();
  });

  it("shows suggestion cards when no active conversation", () => {
    render(<AgentChatView />);
    expect(screen.getByText("How can I help you?")).toBeTruthy();
    expect(screen.getByText("Find remote jobs")).toBeTruthy();
    expect(screen.getByText("Tailor my resume")).toBeTruthy();
    expect(screen.getByText("Interview prep")).toBeTruthy();
    expect(screen.getByText("Score my matches")).toBeTruthy();
  });

  it("loads conversation on sidebar click", async () => {
    vi.mocked(agentService.getConversation).mockResolvedValueOnce(mockConversationDetail);

    render(<AgentChatView />);

    fireEvent.click(screen.getByText("Chat 1"));

    await waitFor(() => {
      expect(agentService.getConversation).toHaveBeenCalledWith(1);
    });

    expect(screen.getByText("Hello")).toBeTruthy();
    expect(screen.getByText("Hi there!")).toBeTruthy();
  });

  it("shows empty conversations message when none exist", () => {
    mockQueries["conversations"] = { data: [] };
    render(<AgentChatView />);
    expect(screen.getByText("No conversations yet")).toBeTruthy();
  });

  it("starts new conversation on new button click", () => {
    render(<AgentChatView />);
    fireEvent.click(screen.getByTitle("New conversation"));

    expect(screen.queryByText("Chat 1")).toBeTruthy();
    expect(screen.getByText("How can I help you?")).toBeTruthy();
  });

  it("sends message on submit via form", async () => {
    vi.mocked(agentService.chatStream).mockImplementationOnce(
      async (_msg, _hist, handlers: any) => {
        handlers.onConversation?.(3);
        handlers.onSection?.({ agent: "chat", type: "message", message: "I can help!" });
        handlers.onDone?.({ conversation_id: 3 });
      },
    );

    render(<AgentChatView />);

    const textarea = screen.getByPlaceholderText(/Message your career assistant/);
    await userEvent.type(textarea, "Find me jobs");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(agentService.chatStream).toHaveBeenCalled();
    });
  });

  it("shows user and assistant messages after submission", async () => {
    vi.mocked(agentService.chatStream).mockImplementationOnce(
      async (_msg, _hist, handlers: any) => {
        handlers.onSection?.({ agent: "chat", type: "message", message: "Here are some jobs" });
        handlers.onDone?.({ conversation_id: 3 });
      },
    );

    render(<AgentChatView />);

    const textarea = screen.getByPlaceholderText(/Message your career assistant/);
    await userEvent.type(textarea, "Find me jobs");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText("Find me jobs")).toBeTruthy();
    });
  });

  it("shows error message when chat fails", async () => {
    vi.mocked(agentService.chatStream).mockImplementationOnce(
      async (_msg, _hist, handlers: any) => {
        handlers.onError?.("Something went wrong");
      },
    );

    render(<AgentChatView />);

    const textarea = screen.getByPlaceholderText(/Message your career assistant/);
    await userEvent.type(textarea, "Hello");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText("Something went wrong")).toBeTruthy();
    });
  });

  it("sends suggestion query on suggestion click", async () => {
    vi.mocked(agentService.chatStream).mockImplementationOnce(
      async (_msg, _hist, handlers: any) => {
        handlers.onDone?.({ conversation_id: 3 });
      },
    );

    render(<AgentChatView />);

    fireEvent.click(screen.getByText("Find remote jobs"));

    await waitFor(() => {
      expect(agentService.chatStream).toHaveBeenCalled();
    });
  });

  it("renders suggestions from assistant result", async () => {
    vi.mocked(agentService.chatStream).mockImplementationOnce(
      async (_msg, _hist, handlers: any) => {
        handlers.onSection?.({ agent: "chat", type: "message", message: "Here you go" });
        handlers.onSuggestions?.(["Tell me more", "Another option"]);
        handlers.onDone?.({ conversation_id: 3 });
      },
    );

    render(<AgentChatView />);

    const textarea = screen.getByPlaceholderText(/Message your career assistant/);
    await userEvent.type(textarea, "Find jobs");
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText("Tell me more")).toBeTruthy();
    });
  });

  it("regenerates when regenerate button clicked", async () => {
    vi.mocked(agentService.getConversation).mockResolvedValueOnce(mockConversationDetail);
    vi.mocked(agentService.chatStream).mockImplementationOnce(
      async (_msg, _hist, handlers: any) => {
        handlers.onDone?.({ conversation_id: 1 });
      },
    );

    render(<AgentChatView />);

    fireEvent.click(screen.getByText("Chat 1"));
    await waitFor(() => {
      expect(screen.getByText("Hello")).toBeTruthy();
    });

    vi.mocked(agentService.chatStream).mockImplementationOnce(
      async (_msg, _hist, handlers: any) => {
        handlers.onDone?.({ conversation_id: 1 });
      },
    );

    const regenerateBtn = screen.getByText("Regenerate");
    fireEvent.click(regenerateBtn);

    await waitFor(() => {
      expect(agentService.chatStream).toHaveBeenCalledTimes(1);
    });
  });
});
