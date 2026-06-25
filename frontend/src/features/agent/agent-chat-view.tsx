"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot, ExternalLink, FileText, MessageSquare, Pencil, Plus, RefreshCw, Search, Send, Sparkles, ThumbsDown, ThumbsUp, Trash2, User, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { DataFields } from "@/components/ui/data-display";
import { agentService, type AgentChatTurn } from "@/services/agent.service";
import { useAuthStore } from "@/stores/auth-store";
import type { AgentJobListing, AgentSection, Conversation } from "@/types/api";
import { cn } from "@/lib/utils";

type ChatMessage =
  | { role: "user"; content: string; id?: number }
  | { role: "assistant"; sections: AgentSection[]; suggestions?: string[]; feedback?: "thumbs_up" | "thumbs_down" | null; id?: number };

const SUGGESTIONS = [
  { title: "Find remote jobs", desc: "Search job boards for roles matching your skills", query: "Find me remote backend jobs" },
  { title: "Tailor my resume", desc: "Customize your resume for a specific role", query: "Tailor my resume for the latest job" },
  { title: "Interview prep", desc: "Get ready with common questions and tips", query: "Prep me for an interview" },
  { title: "Score my matches", desc: "Evaluate how well jobs fit your profile", query: "Score my saved jobs" },
];

export function AgentChatView() {
  const activeWorkspace = useAuthStore((s) => s.activeWorkspace);
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<number | undefined>(undefined);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: conversations } = useQuery({
    queryKey: ["conversations"],
    queryFn: agentService.listConversations,
  });

  const loadConversation = useCallback(async (id: number) => {
    const conv = await agentService.getConversation(id);
    setConversationId(id);
    const msgs: ChatMessage[] = conv.messages.map((m) =>
      m.role === "user"
        ? { role: "user", content: m.content }
        : { role: "assistant", sections: (m.sections ?? []) as AgentSection[] },
    );
    setMessages(msgs);
    setError("");
  }, []);

  const deleteMut = useMutation({
    mutationFn: (id: number) => agentService.deleteConversation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      if (conversationId) {
        setConversationId(undefined);
        setMessages([]);
      }
    },
  });

  const newConversation = () => {
    setConversationId(undefined);
    setMessages([]);
    setError("");
  };

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const submitFromEdit = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;

    const history: AgentChatTurn[] = messages
      .slice(0, -1)
      .map((m) =>
        m.role === "user" ? { role: "user", content: m.content } : { role: "assistant", content: summarize(m.sections) },
      );

    setMessages((prev) => [...prev.slice(0, -1), { role: "user", content: trimmed }, { role: "assistant", sections: [] }]);
    setError("");
    setBusy(true);

    const appendSection = (section: AgentSection) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant") next[next.length - 1] = { role: "assistant", sections: [...last.sections, section] };
        return next;
      });

    const appendDelta = (text: string) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role !== "assistant" || last.sections.length === 0) return next;
        const sections = [...last.sections];
        const tail = sections[sections.length - 1];
        if (tail.type === "message") {
          sections[sections.length - 1] = { ...tail, message: (tail.message ?? "") + text };
          next[next.length - 1] = { role: "assistant", sections, id: last.id };
        }
        return next;
      });

    try {
      await agentService.chatStream(trimmed, history, {
        onConversation: (id) => {
          setConversationId(id);
          queryClient.invalidateQueries({ queryKey: ["conversations"] });
        },
        onSection: appendSection,
        onDelta: appendDelta,
        onSuggestions: (suggestions) =>
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant") next[next.length - 1] = { ...last, suggestions };
            return next;
          }),
        onDone: (data) =>
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant" && data.message_id) next[next.length - 1] = { ...last, id: data.message_id };
            return next;
          }),
        onError: setError,
      }, activeWorkspace?.id, conversationId);
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    } catch {
      setError("The assistant could not complete your request.");
    } finally {
      setBusy(false);
    }
  }, [messages, busy, conversationId, activeWorkspace, queryClient]);

  const regenerate = useCallback(async (index: number) => {
    if (busy || index < 1) return;
    const userMsg = messages[index - 1];
    if (userMsg.role !== "user") return;

    const history: AgentChatTurn[] = messages
      .slice(0, index - 1)
      .map((m) =>
        m.role === "user" ? { role: "user", content: m.content } : { role: "assistant", content: summarize(m.sections) },
      );

    setMessages((prev) => {
      const next = prev.slice(0, index);
      next.push({ role: "assistant", sections: [] });
      return next;
    });
    setError("");
    setBusy(true);

    const appendSection = (section: AgentSection) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant") next[next.length - 1] = { role: "assistant", sections: [...last.sections, section] };
        return next;
      });

    const appendDelta = (text: string) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role !== "assistant" || last.sections.length === 0) return next;
        const sections = [...last.sections];
        const tail = sections[sections.length - 1];
        if (tail.type === "message") {
          sections[sections.length - 1] = { ...tail, message: (tail.message ?? "") + text };
          next[next.length - 1] = { role: "assistant", sections, suggestions: last.suggestions, id: last.id };
        }
        return next;
      });

    try {
      await agentService.chatStream(userMsg.content, history, {
        onConversation: (id) => {
          setConversationId(id);
          queryClient.invalidateQueries({ queryKey: ["conversations"] });
        },
        onSection: appendSection,
        onDelta: appendDelta,
        onSuggestions: (suggestions) =>
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant") next[next.length - 1] = { ...last, suggestions };
            return next;
          }),
        onDone: (data) =>
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant" && data.message_id) next[next.length - 1] = { ...last, id: data.message_id };
            return next;
          }),
        onError: setError,
      }, activeWorkspace?.id, conversationId);
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    } catch {
      setError("The assistant could not complete your request.");
    } finally {
      setBusy(false);
    }
  }, [messages, busy, conversationId, activeWorkspace, queryClient]);

  async function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;

    const history: AgentChatTurn[] = messages.map((m) =>
      m.role === "user" ? { role: "user", content: m.content } : { role: "assistant", content: summarize(m.sections) },
    );

    setMessages((prev) => [...prev, { role: "user", content: trimmed }, { role: "assistant", sections: [] }]);
    setInput("");
    setError("");
    setBusy(true);

    const appendSection = (section: AgentSection) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant") next[next.length - 1] = { role: "assistant", sections: [...last.sections, section] };
        return next;
      });

    const appendDelta = (text: string) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role !== "assistant" || last.sections.length === 0) return next;
        const sections = [...last.sections];
        const tail = sections[sections.length - 1];
        if (tail.type === "message") {
          sections[sections.length - 1] = { ...tail, message: (tail.message ?? "") + text };
          next[next.length - 1] = { role: "assistant", sections, suggestions: last.suggestions, id: last.id };
        }
        return next;
      });

    try {
      await agentService.chatStream(
        trimmed, history,
        {
          onConversation: (id) => {
            setConversationId(id);
            queryClient.invalidateQueries({ queryKey: ["conversations"] });
          },
          onSection: appendSection,
          onDelta: appendDelta,
          onSuggestions: (suggestions) =>
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last?.role === "assistant") next[next.length - 1] = { ...last, suggestions };
              return next;
            }),
          onDone: (data) =>
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last?.role === "assistant" && data.message_id) next[next.length - 1] = { ...last, id: data.message_id };
              return next;
            }),
          onError: setError,
        },
        activeWorkspace?.id,
        conversationId,
      );
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    } catch {
      setError("The assistant could not complete your request.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[calc(100dvh-8rem)] gap-4">
      {/* Conversation sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col overflow-hidden rounded-xl border bg-card sm:flex">
        <div className="flex items-center justify-between border-b px-3 py-2.5">
          <span className="text-sm font-medium">Conversations</span>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={newConversation} title="New conversation">
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {conversations?.map((conv) => (
            <div key={conv.id} className="group flex items-center gap-1">
              <button
                onClick={() => loadConversation(conv.id)}
                className={cn(
                  "flex h-9 flex-1 items-center gap-2 truncate rounded-md px-2 text-left text-sm text-muted-foreground transition hover:bg-accent hover:text-accent-foreground",
                  conv.id === conversationId && "bg-accent text-accent-foreground",
                )}
              >
                <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{conv.title}</span>
              </button>
              <button
                onClick={() => deleteMut.mutate(conv.id)}
                className="hidden h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive group-hover:flex"
                title="Delete"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
          {conversations?.length === 0 && (
            <p className="px-2 py-4 text-center text-xs text-muted-foreground">No conversations yet</p>
          )}
        </div>
      </aside>

      {/* Main chat area */}
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Career Assistant</h1>
          <p className="text-sm text-muted-foreground">Ask in plain language — I&apos;ll find jobs, tailor your resume, or prep you for interviews.</p>
        </div>

        <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
          {messages.length === 0 && !conversationId ? (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 200, damping: 24 }}
              className="flex h-full flex-col items-center justify-center gap-6 text-center"
            >
              <motion.span
                animate={{ scale: [1, 1.08, 1] }}
                transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
                className="grid h-16 w-16 place-items-center rounded-2xl bg-primary/10 text-primary"
              >
                <Sparkles className="h-8 w-8" />
              </motion.span>
              <div className="max-w-sm">
                <h2 className="text-lg font-semibold">How can I help you?</h2>
                <p className="mt-1 text-sm text-muted-foreground">I can find jobs, tailor resumes, prep for interviews, and more.</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <motion.button
                    key={s.query}
                    whileHover={{ scale: 1.03, y: -2 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => submit(s.query)}
                    className="glass-subtle flex flex-col items-start gap-1 rounded-xl border p-4 text-left transition hover:bg-white/40 dark:hover:bg-white/10"
                  >
                    <span className="text-sm font-medium">{s.title}</span>
                    <span className="text-xs text-muted-foreground">{s.desc}</span>
                  </motion.button>
                ))}
              </div>
            </motion.div>
          ) : null}
          {messages.length > 0 ? (
            <motion.div
              variants={{
                hidden: {},
                visible: { transition: { staggerChildren: 0.06 } },
              }}
              initial="hidden"
              animate="visible"
            >
              {messages.map((m, i) => (
            <MessageBubble
              key={i}
              message={m}
              busy={busy && i === messages.length - 1}
              isLast={i === messages.length - 1}
              onEdit={
                m.role === "user" && !busy
                  ? (content) => {
                      setMessages((prev) => {
                        const next = prev.slice(0, i);
                        next.push({ role: "user", content });
                        return next;
                      });
                      submitFromEdit(content);
                    }
                  : undefined
              }
              onRegenerate={
                m.role === "assistant" && !busy && i === messages.length - 1
                  ? () => regenerate(i)
                  : undefined
              }
              onFeedback={
                m.role === "assistant" && !busy && conversationId && m.id
                  ? (rating) => {
                      setMessages((prev) => {
                        const next = [...prev];
                        const msg = next[i];
                        if (msg.role === "assistant") next[i] = { ...msg, feedback: rating };
                        return next;
                      });
                      agentService.recordFeedback(conversationId, m.id!, rating).catch(() => {});
                    }
                  : undefined
              }
              onSuggestionClick={
                !busy ? (query) => {
                  const textarea = document.querySelector<HTMLTextAreaElement>("textarea");
                  if (textarea) {
                    textarea.value = query;
                    textarea.focus();
                  }
                  // Optionally submit directly:
                  submit(query);
                } : undefined
              }
            />
          ))}
            </motion.div>
          ) : null}
          {error ? <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-sm text-destructive">{error}</motion.div> : null}
        </div>

        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit(input);
          }}
        >
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(input);
              }
            }}
            placeholder="Message your career assistant…"
            rows={1}
            className="max-h-32 min-h-[44px] flex-1 resize-none"
          />
          <Button type="submit" disabled={!input.trim() || busy} size="icon" className="h-11 w-11 shrink-0">
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </div>
    </div>
  );
}

function summarize(sections: AgentSection[]): string {
  return sections.map((s) => s.message || `[${s.type}]`).join(" ");
}

function Thinking() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-3 text-sm text-muted-foreground"
    >
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/10 text-primary">
        <Bot className="h-4 w-4" />
      </span>
      <span className="flex items-center gap-1">
        Thinking
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="inline-block h-1 w-1 rounded-full bg-muted-foreground"
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{ repeat: Infinity, duration: 1.4, delay: i * 0.2, ease: "easeInOut" }}
          />
        ))}
      </span>
    </motion.div>
  );
}

const bubbleVariants = {
  hidden: { opacity: 0, y: 16, scale: 0.97 },
  visible: { opacity: 1, y: 0, scale: 1, transition: { type: "spring" as const, stiffness: 260, damping: 24 } },
};

function MessageBubble({
  message, busy, onEdit, onRegenerate, isLast, onFeedback, onSuggestionClick,
}: {
  message: ChatMessage; busy: boolean; onEdit?: (content: string) => void; onRegenerate?: () => void; isLast?: boolean;
  onFeedback?: (rating: "thumbs_up" | "thumbs_down") => void;
  onSuggestionClick?: (query: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(message.role === "user" ? message.content : "");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.setSelectionRange(inputRef.current.value.length, inputRef.current.value.length);
    }
  }, [editing]);

  if (message.role === "user") {
    if (editing) {
      return (
        <motion.div variants={bubbleVariants} initial="hidden" animate="visible" className="flex justify-end gap-2">
          <div className="flex max-w-[80%] flex-col gap-2">
            <Textarea
              ref={inputRef}
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              className="min-h-[60px] resize-none text-sm"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onEdit?.(editText);
                  setEditing(false);
                }
              }}
            />
            <div className="flex justify-end gap-1">
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setEditing(false)}>
                <X className="mr-1 h-3 w-3" />Cancel
              </Button>
              <Button size="sm" className="h-7 text-xs" onClick={() => { onEdit?.(editText); setEditing(false); }}>
                Save
              </Button>
            </div>
          </div>
          <span className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground"><User className="h-4 w-4" /></span>
        </motion.div>
      );
    }
    return (
      <motion.div variants={bubbleVariants} initial="hidden" animate="visible" className="group flex justify-end gap-2">
        <div className="flex items-start gap-1">
          <div className="glass-subtle max-w-[80%] rounded-2xl rounded-br-sm px-4 py-2.5 text-sm">{message.content}</div>
          <button
            onClick={() => { setEditText(message.content); setEditing(true); }}
            className="mt-1 hidden h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-accent group-hover:flex"
            title="Edit"
          >
            <Pencil className="h-3 w-3" />
          </button>
        </div>
        <span className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground"><User className="h-4 w-4" /></span>
      </motion.div>
    );
  }
  return (
    <motion.div variants={bubbleVariants} initial="hidden" animate="visible" className="group flex gap-2">
      <span className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><Bot className="h-4 w-4" /></span>
      <div className="min-w-0 flex-1 space-y-3">
        {message.sections.map((section, i) => (
          <SectionView key={i} section={section} />
        ))}
        {busy ? <Thinking /> : null}
        {!busy && isLast && onRegenerate ? (
          <div className="flex items-center gap-2">
            <button
              onClick={onRegenerate}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              title="Regenerate"
            >
              <RefreshCw className="h-3 w-3" />Regenerate
            </button>
            <span className="text-xs text-muted-foreground/50">|</span>
            <button
              onClick={() => onFeedback?.("thumbs_up")}
              className={`flex items-center gap-1 text-xs hover:text-foreground ${
                message.feedback === "thumbs_up" ? "text-primary" : "text-muted-foreground"
              }`}
              title="Helpful"
            >
              <ThumbsUp className="h-3 w-3" />
            </button>
            <button
              onClick={() => onFeedback?.("thumbs_down")}
              className={`flex items-center gap-1 text-xs hover:text-foreground ${
                message.feedback === "thumbs_down" ? "text-destructive" : "text-muted-foreground"
              }`}
              title="Not helpful"
            >
              <ThumbsDown className="h-3 w-3" />
            </button>
          </div>
        ) : null}
        {!busy && message.suggestions && message.suggestions.length > 0 ? (
          <div className="flex flex-wrap gap-2 pt-1">
            {message.suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => onSuggestionClick?.(s)}
                className="rounded-full border bg-background px-3 py-1 text-xs text-muted-foreground transition hover:border-primary hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}

function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none dark:prose-invert prose-p:leading-relaxed prose-pre:rounded-lg">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}

function SectionView({ section }: { section: AgentSection }) {
  if (section.type === "listings") {
    const listings = (section.data as AgentJobListing[]) ?? [];
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-medium"><Search className="h-4 w-4 text-primary" />{section.message}</div>
        <div className="space-y-2">
          {listings.map((job, i) => (
            <Card key={job.url ?? job.title ?? i}>
              <CardContent className="flex items-start justify-between gap-3 p-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{job.title}</div>
                  <div className="truncate text-xs text-muted-foreground">{[job.company, job.location, job.source].filter(Boolean).join(" · ")}</div>
                  {job.good_fit ? <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{job.good_fit}</div> : null}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">{job.match_score}%</span>
                  {job.url ? <a href={job.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ExternalLink className="h-3 w-3" />Open</a> : null}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (section.type === "tailored_resume" || section.type === "interview_prep") {
    const Icon = section.type === "tailored_resume" ? FileText : MessageSquare;
    const label = section.type === "tailored_resume" ? "Tailored resume" : "Interview prep";
    return (
      <Card>
        <CardContent className="space-y-2 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-medium"><Icon className="h-4 w-4 text-primary" />{label}{section.job?.company ? ` — ${section.job.company}` : ""}</div>
            {section.job?.id ? <Link href={`/opportunities/${section.job.id}`} className="text-xs text-muted-foreground hover:text-foreground">View →</Link> : null}
          </div>
          <DataFields data={(section.data as Record<string, unknown>) ?? {}} />
        </CardContent>
      </Card>
    );
  }

  if (section.type === "error") {
    return <div className="text-sm text-destructive">{section.message}</div>;
  }

  return (
    <div className="glass-subtle max-w-[90%] rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm">
      {section.message ? <MarkdownMessage content={section.message} /> : null}
    </div>
  );
}
