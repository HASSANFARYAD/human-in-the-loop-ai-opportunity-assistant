"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Bot, Briefcase, CalendarClock, ClipboardCheck, Sparkles, Workflow } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SourceChart, ScoreDistribution, TrendChart } from "@/components/charts/analytics-charts";
import { opportunityService } from "@/services/opportunity.service";
import { automationService } from "@/services/automation.service";
import { providerService } from "@/services/provider.service";

function Kpi({ label, value, icon: Icon }: { label: string; value: string | number; icon: typeof Briefcase }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-5">
        <div>
          <div className="text-sm text-muted-foreground">{label}</div>
          <div className="mt-2 text-2xl font-semibold">{value}</div>
        </div>
        <span className="grid h-10 w-10 place-items-center rounded-md bg-primary/10 text-primary"><Icon className="h-5 w-5" /></span>
      </CardContent>
    </Card>
  );
}

export function DashboardView() {
  const jobs = useQuery({ queryKey: ["opportunities"], queryFn: () => opportunityService.list() });
  const rules = useQuery({ queryKey: ["automation-rules"], queryFn: () => automationService.rules() });
  const generations = useQuery({ queryKey: ["ai-generations"], queryFn: () => providerService.generations() });

  const opportunities = jobs.data ?? [];
  const chartData = useMemo(() => {
    const sources = Object.entries(opportunities.reduce<Record<string, number>>((acc, item) => {
      acc[item.source || "unknown"] = (acc[item.source || "unknown"] ?? 0) + 1;
      return acc;
    }, {})).map(([name, value]) => ({ name, value }));
    const buckets = ["0-39", "40-59", "60-79", "80-100"].map((bucket) => ({ bucket, count: 0 }));
    opportunities.forEach((item) => {
      const score = Number(item.match_score ?? item.score ?? 0);
      buckets[score >= 80 ? 3 : score >= 60 ? 2 : score >= 40 ? 1 : 0].count += 1;
    });
    return { sources, buckets };
  }, [opportunities]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">AI activity, deadlines, scoring, and automation health across your workspace.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <Kpi label="Total Opportunities" value={opportunities.length} icon={Briefcase} />
        <Kpi label="High Match" value={opportunities.filter((j) => Number(j.match_score ?? j.score ?? 0) >= 80).length} icon={Sparkles} />
        <Kpi label="Pending Reviews" value={opportunities.filter((j) => (j.status ?? "new").includes("review")).length} icon={ClipboardCheck} />
        <Kpi label="Upcoming Deadlines" value={opportunities.filter((j) => j.deadline).length} icon={CalendarClock} />
        <Kpi label="Active Automations" value={(rules.data ?? []).filter((r) => r.is_active).length} icon={Workflow} />
        <Kpi label="AI Activity" value={(generations.data ?? []).length} icon={Bot} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Opportunity Sources</CardTitle></CardHeader><CardContent><SourceChart data={chartData.sources.length ? chartData.sources : [{ name: "No data", value: 1 }]} /></CardContent></Card>
        <Card><CardHeader><CardTitle>Match Score Distribution</CardTitle></CardHeader><CardContent><ScoreDistribution data={chartData.buckets} /></CardContent></Card>
        <Card><CardHeader><CardTitle>Weekly Activity</CardTitle></CardHeader><CardContent><TrendChart data={[{ name: "Mon", value: 2 }, { name: "Tue", value: 4 }, { name: "Wed", value: opportunities.length }, { name: "Thu", value: 3 }, { name: "Fri", value: 6 }]} /></CardContent></Card>
        <Card><CardHeader><CardTitle>Automation Statistics</CardTitle></CardHeader><CardContent><TrendChart data={[{ name: "Rules", value: rules.data?.length ?? 0 }, { name: "Runs", value: 0 }, { name: "Failures", value: 0 }]} /></CardContent></Card>
      </div>
    </div>
  );
}
