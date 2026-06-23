"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bot, ExternalLink, FileText, MessageSquare, Search, Send, Sparkles, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { DataFields } from "@/components/ui/data-display";
import { agentService, type AgentChatTurn } from "@/services/agent.service";
import { useAuthStore } from "@/stores/auth-store";
import type { AgentJobListing, AgentSection } from "@/types/api";

type ChatMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; sections: AgentSection[] };

const SUGGESTIONS = [
  "Find me remote backend jobs",
  "Tailor my resume for the latest job",
  "Prep me for an interview",
];

export function AgentChatView() {
  const activeWorkspace = useAuthStore((s) => s.activeWorkspace);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;

    const history: AgentChatTurn[] = messages.map((m) =>
      m.role === "user" ? { role: "user", content: m.content } : { role: "assistant", content: summarize(m.sections) },
    );

    // Append the user turn and an empty assistant turn we stream sections into.
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

    // Token-style streaming: append delta text to the trailing message section.
    const appendDelta = (text: string) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role !== "assistant" || last.sections.length === 0) return next;
        const sections = [...last.sections];
        const tail = sections[sections.length - 1];
        if (tail.type === "message") {
          sections[sections.length - 1] = { ...tail, message: (tail.message ?? "") + text };
          next[next.length - 1] = { role: "assistant", sections };
        }
        return next;
      });

    try {
      await agentService.chatStream(trimmed, history, { onSection: appendSection, onDelta: appendDelta, onError: setError }, activeWorkspace?.id);
    } catch {
      setError("The assistant could not complete your request.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[calc(100dvh-8rem)] flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Career Assistant</h1>
        <p className="text-sm text-muted-foreground">Ask in plain language — I&apos;ll find jobs, tailor your resume, or prep you for interviews.</p>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <span className="grid h-12 w-12 place-items-center rounded-full bg-primary/10 text-primary"><Sparkles className="h-6 w-6" /></span>
            <div className="text-sm text-muted-foreground">Try one of these:</div>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => submit(s)} className="glass-subtle rounded-full px-4 py-2 text-sm transition hover:bg-white/40 dark:hover:bg-white/10">{s}</button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => <MessageBubble key={i} message={m} busy={busy && i === messages.length - 1} />)
        )}
        {error ? <div className="text-sm text-destructive">{error}</div> : null}
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
  );
}

function summarize(sections: AgentSection[]): string {
  return sections.map((s) => s.message || `[${s.type}]`).join(" ");
}

function Thinking() {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <Bot className="h-4 w-4 animate-pulse text-primary" /> Thinking…
    </div>
  );
}

function MessageBubble({ message, busy }: { message: ChatMessage; busy: boolean }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end gap-2">
        <div className="glass-subtle max-w-[80%] rounded-2xl rounded-br-sm px-4 py-2.5 text-sm">{message.content}</div>
        <span className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground"><User className="h-4 w-4" /></span>
      </div>
    );
  }
  return (
    <div className="flex gap-2">
      <span className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><Bot className="h-4 w-4" /></span>
      <div className="min-w-0 flex-1 space-y-3">
        {message.sections.map((section, i) => (
          <SectionView key={i} section={section} />
        ))}
        {busy ? <Thinking /> : null}
      </div>
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

  return <div className="glass-subtle max-w-[80%] rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm">{section.message}</div>;
}
