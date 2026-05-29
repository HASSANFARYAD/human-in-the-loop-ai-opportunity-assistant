"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreDistribution, SourceChart, TrendChart } from "@/components/charts/analytics-charts";
import { opportunityService } from "@/services/opportunity.service";
import { automationService } from "@/services/automation.service";
import { providerService } from "@/services/provider.service";

export function AnalyticsView() {
  const jobs = useQuery({ queryKey: ["opportunities"], queryFn: () => opportunityService.list() });
  const runs = useQuery({ queryKey: ["automation-runs"], queryFn: () => automationService.runs() });
  const generations = useQuery({ queryKey: ["ai-generations"], queryFn: () => providerService.generations() });
  const data = useMemo(() => {
    const items = jobs.data ?? [];
    const byType = Object.entries(items.reduce<Record<string, number>>((acc, item) => { acc[item.opportunity_type || "job"] = (acc[item.opportunity_type || "job"] ?? 0) + 1; return acc; }, {})).map(([name, value]) => ({ name, value }));
    const bySource = Object.entries(items.reduce<Record<string, number>>((acc, item) => { acc[item.source || "unknown"] = (acc[item.source || "unknown"] ?? 0) + 1; return acc; }, {})).map(([name, value]) => ({ name, value }));
    const buckets = ["0-39", "40-59", "60-79", "80-100"].map((bucket) => ({ bucket, count: 0 }));
    items.forEach((item) => { const score = Number(item.match_score ?? item.score ?? 0); buckets[score >= 80 ? 3 : score >= 60 ? 2 : score >= 40 ? 1 : 0].count += 1; });
    return { byType, bySource, buckets };
  }, [jobs.data]);
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Analytics</h1><p className="text-sm text-muted-foreground">Opportunities by type/source, match trends, user activity, automation activity, and AI usage.</p></div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Opportunities by Type</CardTitle></CardHeader><CardContent><SourceChart data={data.byType.length ? data.byType : [{ name: "No data", value: 1 }]} /></CardContent></Card>
        <Card><CardHeader><CardTitle>Opportunities by Source</CardTitle></CardHeader><CardContent><SourceChart data={data.bySource.length ? data.bySource : [{ name: "No data", value: 1 }]} /></CardContent></Card>
        <Card><CardHeader><CardTitle>Match Trends</CardTitle></CardHeader><CardContent><ScoreDistribution data={data.buckets} /></CardContent></Card>
        <Card><CardHeader><CardTitle>Automation Activity</CardTitle></CardHeader><CardContent><TrendChart data={[{ name: "Runs", value: runs.data?.length ?? 0 }, { name: "AI", value: generations.data?.length ?? 0 }, { name: "Opportunities", value: jobs.data?.length ?? 0 }]} /></CardContent></Card>
      </div>
    </div>
  );
}
