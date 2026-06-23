"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, FileCode2, Gauge, HeartPulse, History } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataFields, DataTable, formatDisplayValue } from "@/components/ui/data-display";
import { providerService } from "@/services/provider.service";

export function AIWorkspaceView() {
  const generations = useQuery({ queryKey: ["ai-generations"], queryFn: () => providerService.generations() });
  const prompts = useQuery({ queryKey: ["ai-prompts"], queryFn: providerService.prompts });
  const health = useQuery({ queryKey: ["ai-health"], queryFn: providerService.aiHealth });
  const usage = useQuery({ queryKey: ["ai-usage"], queryFn: providerService.usage });
  const usageLabel = usage.data
    ? usage.data.unlimited
      ? `${usage.data.used} (unlimited)`
      : `${usage.data.used} / ${usage.data.limit}`
    : "—";
  const usageWarning = !!usage.data && !usage.data.unlimited && (usage.data.remaining ?? 0) <= 0;
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">AI Workspace</h1><p className="text-sm text-muted-foreground">Generation history, prompt versions, provider health, AI logs, and activity timeline.</p></div>
      <div className="grid gap-4 md:grid-cols-4">
        <Card><CardContent className="p-5"><Gauge className={`mb-3 h-5 w-5 ${usageWarning ? "text-destructive" : "text-primary"}`} /><div className="text-2xl font-semibold">{usageLabel}</div><div className="text-sm text-muted-foreground">{usageWarning ? "Daily limit reached" : "AI generations today"}</div></CardContent></Card>
        <Card><CardContent className="p-5"><History className="mb-3 h-5 w-5 text-primary" /><div className="text-2xl font-semibold">{generations.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Generations</div></CardContent></Card>
        <Card><CardContent className="p-5"><FileCode2 className="mb-3 h-5 w-5 text-success" /><div className="text-2xl font-semibold">{prompts.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Prompt versions</div></CardContent></Card>
        <Card><CardContent className="p-5"><HeartPulse className="mb-3 h-5 w-5 text-warning" /><div className="text-2xl font-semibold">{String(health.data?.status ?? "unknown")}</div><div className="text-sm text-muted-foreground">Provider health</div></CardContent></Card>
      </div>
      <Card><CardHeader><CardTitle>Provider Route</CardTitle></CardHeader><CardContent><DataFields data={health.data ?? {}} /></CardContent></Card>
      <Card><CardHeader><CardTitle>Prompt Versions</CardTitle></CardHeader><CardContent><DataTable rows={(prompts.data ?? []) as Record<string, unknown>[]} columns={["name", "version", "status", "updated_at"]} /></CardContent></Card>
      <Card><CardHeader><CardTitle>AI Activity Timeline</CardTitle></CardHeader><CardContent className="space-y-3">{(generations.data ?? []).length ? (generations.data ?? []).map((item, index) => <div key={index} className="flex gap-3 rounded-md border p-3"><Bot className="mt-0.5 h-4 w-4 text-primary" /><div className="grid gap-1 text-sm">{Object.entries((item ?? {}) as Record<string, unknown>).map(([key, value]) => <div key={key}><span className="font-medium">{key.replace(/_/g, " ")}:</span> {formatDisplayValue(value)}</div>)}</div></div>) : <div className="text-sm text-muted-foreground">No data available</div>}</CardContent></Card>
    </div>
  );
}
