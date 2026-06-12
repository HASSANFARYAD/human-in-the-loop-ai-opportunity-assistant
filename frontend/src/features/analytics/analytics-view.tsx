"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreDistribution, SourceChart } from "@/components/charts/analytics-charts";
import { opportunityService } from "@/services/opportunity.service";

export function AnalyticsView() {
  const jobs = useQuery({ queryKey: ["opportunities"], queryFn: () => opportunityService.list() });
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
      <div><h1 className="text-2xl font-semibold">Insights</h1><p className="text-sm text-muted-foreground">Saved jobs by type/source and match score trends.</p></div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Jobs by Type</CardTitle></CardHeader><CardContent><SourceChart data={data.byType.length ? data.byType : [{ name: "No data", value: 1 }]} /></CardContent></Card>
        <Card><CardHeader><CardTitle>Jobs by Source</CardTitle></CardHeader><CardContent><SourceChart data={data.bySource.length ? data.bySource : [{ name: "No data", value: 1 }]} /></CardContent></Card>
        <Card><CardHeader><CardTitle>Match Trends</CardTitle></CardHeader><CardContent><ScoreDistribution data={data.buckets} /></CardContent></Card>
      </div>
    </div>
  );
}
