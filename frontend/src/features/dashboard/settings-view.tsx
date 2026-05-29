"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Activity, HeartPulse, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { auditService } from "@/services/audit.service";
import { feedbackService } from "@/services/feedback.service";

export function SettingsView() {
  const tab = useSearchParams().get("tab") ?? "settings";
  const audit = useQuery({ queryKey: ["audit"], queryFn: () => auditService.logs() });
  const health = useQuery({ queryKey: ["health"], queryFn: auditService.health });
  const usage = useQuery({ queryKey: ["usage"], queryFn: auditService.usage });
  const feedback = useQuery({ queryKey: ["feedback"], queryFn: () => feedbackService.list() });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">System</h1><p className="text-sm text-muted-foreground">Feedback, audit logs, usage, health, and runtime settings.</p></div>
      <div className="grid gap-4 md:grid-cols-3">
        <Card><CardContent className="p-5"><HeartPulse className="mb-3 h-5 w-5 text-success" /><div className="text-2xl font-semibold">{String(health.data?.status ?? "unknown")}</div><div className="text-sm text-muted-foreground">Health</div></CardContent></Card>
        <Card><CardContent className="p-5"><ShieldCheck className="mb-3 h-5 w-5 text-primary" /><div className="text-2xl font-semibold">{audit.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Audit events</div></CardContent></Card>
        <Card><CardContent className="p-5"><Activity className="mb-3 h-5 w-5 text-warning" /><div className="text-2xl font-semibold">{feedback.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Feedback items</div></CardContent></Card>
      </div>
      {tab === "feedback" ? (
        <Card><CardHeader><CardTitle>Feedback</CardTitle></CardHeader><CardContent><pre className="overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(feedback.data ?? [], null, 2)}</pre></CardContent></Card>
      ) : tab === "audit" ? (
        <Card><CardHeader><CardTitle>Audit Logs</CardTitle></CardHeader><CardContent><pre className="overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(audit.data ?? [], null, 2)}</pre></CardContent></Card>
      ) : tab === "usage" ? (
        <Card><CardHeader><CardTitle>Usage</CardTitle></CardHeader><CardContent><pre className="overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(usage.data ?? {}, null, 2)}</pre></CardContent></Card>
      ) : tab === "health" ? (
        <Card><CardHeader><CardTitle>Health</CardTitle></CardHeader><CardContent><pre className="overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(health.data ?? {}, null, 2)}</pre></CardContent></Card>
      ) : (
        <Card><CardHeader><CardTitle>Settings</CardTitle></CardHeader><CardContent className="text-sm text-muted-foreground">Runtime settings are managed by backend environment variables and deployment configuration.</CardContent></Card>
      )}
    </div>
  );
}
