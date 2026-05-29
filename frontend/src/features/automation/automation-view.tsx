"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Play, Workflow } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { automationService } from "@/services/automation.service";
import { formatDate } from "@/lib/utils";

export function AutomationView() {
  const rules = useQuery({ queryKey: ["automation-rules"], queryFn: () => automationService.rules() });
  const runs = useQuery({ queryKey: ["automation-runs"], queryFn: () => automationService.runs() });
  const errors = useQuery({ queryKey: ["automation-errors"], queryFn: () => automationService.errors() });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Automation</h1><p className="text-sm text-muted-foreground">Rules, scheduled jobs, approvals, recent runs, failures, and success rates.</p></div>
      <div className="grid gap-4 md:grid-cols-4">
        <Card><CardContent className="p-5"><Workflow className="mb-3 h-5 w-5 text-primary" /><div className="text-2xl font-semibold">{rules.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Rules</div></CardContent></Card>
        <Card><CardContent className="p-5"><CheckCircle2 className="mb-3 h-5 w-5 text-success" /><div className="text-2xl font-semibold">{(runs.data ?? []).filter((r) => r.status === "success").length}</div><div className="text-sm text-muted-foreground">Successful runs</div></CardContent></Card>
        <Card><CardContent className="p-5"><AlertTriangle className="mb-3 h-5 w-5 text-warning" /><div className="text-2xl font-semibold">{errors.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Failures</div></CardContent></Card>
        <Card><CardContent className="p-5"><Play className="mb-3 h-5 w-5 text-primary" /><div className="text-2xl font-semibold">{runs.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Recent runs</div></CardContent></Card>
      </div>
      <Card><CardHeader><CardTitle>Automation Rules</CardTitle></CardHeader><CardContent className="space-y-3">{(rules.data ?? []).map((rule) => <div key={rule.id} className="flex items-center justify-between rounded-md border p-3"><div><div className="font-medium">{rule.name}</div><div className="text-sm text-muted-foreground">{rule.trigger_event} → {rule.action_type}</div></div><Badge>{rule.is_active ? "active" : "inactive"}</Badge></div>)}</CardContent></Card>
      <Card><CardHeader><CardTitle>Recent Runs</CardTitle></CardHeader><CardContent className="space-y-3">{(runs.data ?? []).map((run) => <div key={run.id} className="rounded-md border p-3"><div className="flex justify-between"><span className="font-medium">Run #{run.id}</span><Badge>{run.status}</Badge></div><div className="text-sm text-muted-foreground">{run.trigger_event || "manual"} · {formatDate(run.started_at)}</div></div>)}</CardContent></Card>
    </div>
  );
}
