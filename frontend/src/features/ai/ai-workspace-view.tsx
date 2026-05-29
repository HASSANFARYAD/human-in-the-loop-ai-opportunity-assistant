"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, FileCode2, HeartPulse, History } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { providerService } from "@/services/provider.service";

export function AIWorkspaceView() {
  const generations = useQuery({ queryKey: ["ai-generations"], queryFn: () => providerService.generations() });
  const prompts = useQuery({ queryKey: ["ai-prompts"], queryFn: providerService.prompts });
  const health = useQuery({ queryKey: ["ai-health"], queryFn: providerService.aiHealth });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">AI Workspace</h1><p className="text-sm text-muted-foreground">Generation history, prompt versions, provider health, AI logs, and activity timeline.</p></div>
      <div className="grid gap-4 md:grid-cols-3">
        <Card><CardContent className="p-5"><History className="mb-3 h-5 w-5 text-primary" /><div className="text-2xl font-semibold">{generations.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Generations</div></CardContent></Card>
        <Card><CardContent className="p-5"><FileCode2 className="mb-3 h-5 w-5 text-success" /><div className="text-2xl font-semibold">{prompts.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Prompt versions</div></CardContent></Card>
        <Card><CardContent className="p-5"><HeartPulse className="mb-3 h-5 w-5 text-warning" /><div className="text-2xl font-semibold">{String(health.data?.status ?? "unknown")}</div><div className="text-sm text-muted-foreground">Provider health</div></CardContent></Card>
      </div>
      <Card><CardHeader><CardTitle>Provider Route</CardTitle></CardHeader><CardContent><pre className="overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(health.data ?? {}, null, 2)}</pre></CardContent></Card>
      <Card><CardHeader><CardTitle>AI Activity Timeline</CardTitle></CardHeader><CardContent className="space-y-3">{(generations.data ?? []).map((item, index) => <div key={index} className="flex gap-3 rounded-md border p-3"><Bot className="mt-0.5 h-4 w-4 text-primary" /><pre className="overflow-auto text-xs">{JSON.stringify(item, null, 2)}</pre></div>)}</CardContent></Card>
    </div>
  );
}
