"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreBadge } from "@/components/ui/score-badge";
import { ScoreDistribution, SourceChart } from "@/components/charts/analytics-charts";
import { opportunityService } from "@/services/opportunity.service";
import { staggerItem } from "@/lib/animation";

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1, delayChildren: 0.1 } },
};

export function AnalyticsView() {
  const jobs = useQuery({ queryKey: ["opportunities"], queryFn: () => opportunityService.list() });
  const data = useMemo(() => {
    const items = jobs.data ?? [];
    const scores = items.map((item) => Number(item.match_score ?? item.score ?? 0));
    const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
    const byType = Object.entries(items.reduce<Record<string, number>>((acc, item) => { acc[item.opportunity_type || "job"] = (acc[item.opportunity_type || "job"] ?? 0) + 1; return acc; }, {})).map(([name, value]) => ({ name, value }));
    const bySource = Object.entries(items.reduce<Record<string, number>>((acc, item) => { acc[item.source || "unknown"] = (acc[item.source || "unknown"] ?? 0) + 1; return acc; }, {})).map(([name, value]) => ({ name, value }));
    const buckets = ["0-39", "40-59", "60-79", "80-100"].map((bucket) => ({ bucket, count: 0 }));
    items.forEach((item) => { const score = Number(item.match_score ?? item.score ?? 0); buckets[score >= 80 ? 3 : score >= 60 ? 2 : score >= 40 ? 1 : 0].count += 1; });
    return { avg, scoredCount: scores.filter((s) => s > 0).length, byType, bySource, buckets };
  }, [jobs.data]);
  return (
    <motion.div variants={container} initial="hidden" animate="visible" className="space-y-5">
      <motion.div variants={staggerItem}>
        <h1 className="text-2xl font-semibold">Insights</h1>
        <p className="text-sm text-muted-foreground">Saved jobs by type/source and match score trends.</p>
      </motion.div>
      <motion.div variants={container} initial="hidden" animate="visible" className="grid gap-4 sm:grid-cols-3">
        <motion.div variants={staggerItem}>
          <Card><CardContent className="flex flex-col items-center gap-3 p-5 text-center">
            <span className="text-xs font-medium text-muted-foreground">Average Match</span>
            <ScoreBadge score={data.avg} size="lg" />
          </CardContent></Card>
        </motion.div>
        <motion.div variants={staggerItem}>
          <Card><CardContent className="flex flex-col items-center gap-3 p-5 text-center">
            <span className="text-xs font-medium text-muted-foreground">Scored Jobs</span>
            <span className="text-3xl font-semibold tabular-nums text-primary">{data.scoredCount}</span>
          </CardContent></Card>
        </motion.div>
        <motion.div variants={staggerItem}>
          <Card><CardContent className="flex flex-col items-center gap-3 p-5 text-center">
            <span className="text-xs font-medium text-muted-foreground">High Match (80+)</span>
            <span className="text-3xl font-semibold tabular-nums text-emerald-500">{data.buckets[3].count}</span>
          </CardContent></Card>
        </motion.div>
      </motion.div>
      <motion.div variants={container} initial="hidden" animate="visible" className="grid gap-4 lg:grid-cols-2">
        <motion.div variants={staggerItem}>
          <Card><CardHeader><CardTitle>Jobs by Type</CardTitle></CardHeader><CardContent><SourceChart data={data.byType.length ? data.byType : [{ name: "No data", value: 1 }]} /></CardContent></Card>
        </motion.div>
        <motion.div variants={staggerItem}>
          <Card><CardHeader><CardTitle>Jobs by Source</CardTitle></CardHeader><CardContent><SourceChart data={data.bySource.length ? data.bySource : [{ name: "No data", value: 1 }]} /></CardContent></Card>
        </motion.div>
        <motion.div variants={staggerItem}>
          <Card><CardHeader><CardTitle>Match Trends</CardTitle></CardHeader><CardContent><ScoreDistribution data={data.buckets} /></CardContent></Card>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}
