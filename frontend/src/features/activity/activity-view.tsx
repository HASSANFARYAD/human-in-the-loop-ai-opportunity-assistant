"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, MessageSquare, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { auditService } from "@/services/audit.service";
import { feedbackService } from "@/services/feedback.service";
import { formatDate } from "@/lib/utils";

export function ActivityView() {
  const audit = useQuery({ queryKey: ["activity-audit"], queryFn: () => auditService.logs(undefined, 50) });
  const feedback = useQuery({ queryKey: ["activity-feedback"], queryFn: () => feedbackService.list(undefined, 50) });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Activity Feed</h1>
        <p className="text-sm text-muted-foreground">Recent audit events and feedback activity across your workspace.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" /> Audit Events</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {(audit.data ?? []).map((item) => (
              <div key={item.id} className="rounded-md border p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">{item.action}</span>
                  <Badge>{item.resource_type || "system"}</Badge>
                </div>
                <div className="text-sm text-muted-foreground">{formatDate(item.created_at)}</div>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><MessageSquare className="h-4 w-4 text-primary" /> Feedback</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {(feedback.data ?? []).map((item) => (
              <div key={item.id} className="rounded-md border p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">{item.title}</span>
                  <Badge>{item.status || item.severity}</Badge>
                </div>
                <div className="text-sm text-muted-foreground">{item.category} · {formatDate(item.created_at)}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      {!(audit.data?.length || feedback.data?.length) ? (
        <Card><CardContent className="flex items-center gap-3 p-5 text-sm text-muted-foreground"><Activity className="h-4 w-4" /> No recent activity found.</CardContent></Card>
      ) : null}
    </div>
  );
}
