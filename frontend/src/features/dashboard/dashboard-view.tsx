"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Briefcase, CalendarClock, ClipboardCheck, Sparkles, Timer } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SourceChart, ScoreDistribution, TrendChart } from "@/components/charts/analytics-charts";
import { NextBestAction } from "@/components/ui/next-best-action";
import { Skeleton, SkeletonKPIRow, SkeletonChart } from "@/components/ui/skeleton";
import { opportunityService } from "@/services/opportunity.service";
import { staggerItem } from "@/lib/animation";
import { cn } from "@/lib/utils";

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

const chartContainer = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1, delayChildren: 0.3 } },
};

function Kpi({ label, value, icon: Icon, urgent }: { label: string; value: string | number; icon: typeof Briefcase; urgent?: boolean }) {
  return (
    <motion.div variants={staggerItem}>
      <Card>
        <CardContent className="flex items-center justify-between p-5">
          <div>
            <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
              {urgent ? <Timer className="h-3.5 w-3.5 text-destructive" /> : null}
              {label}
            </div>
            <div className={cn("mt-2 text-2xl font-semibold tabular-nums", urgent && value !== 0 && Number(value) > 0 && "text-destructive")}>
              {value}
            </div>
          </div>
          <motion.span
            whileHover={{ rotate: 12, scale: 1.15 }}
            transition={{ type: "spring", stiffness: 300, damping: 15 }}
            className={cn(
              "grid h-10 w-10 place-items-center rounded-md",
              urgent ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary",
            )}
          >
            <Icon className="h-5 w-5" />
          </motion.span>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export function DashboardView() {
  const jobs = useQuery({ queryKey: ["opportunities"], queryFn: () => opportunityService.list() });

  const savedJobs = useMemo(() => jobs.data ?? [], [jobs.data]);
  const chartData = useMemo(() => {
    const sources = Object.entries(savedJobs.reduce<Record<string, number>>((acc, item) => {
      acc[item.source || "unknown"] = (acc[item.source || "unknown"] ?? 0) + 1;
      return acc;
    }, {})).map(([name, value]) => ({ name, value }));
    const buckets = ["0-39", "40-59", "60-79", "80-100"].map((bucket) => ({ bucket, count: 0 }));
    savedJobs.forEach((item) => {
      const score = Number(item.match_score ?? item.score ?? 0);
      buckets[score >= 80 ? 3 : score >= 60 ? 2 : score >= 40 ? 1 : 0].count += 1;
    });
    const weekly = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((name) => ({ name, value: 0 }));
    savedJobs.forEach((item) => {
      const date = item.created_at ? new Date(item.created_at) : null;
      if (date && !Number.isNaN(date.getTime())) weekly[date.getDay()].value += 1;
    });
    return { sources, buckets, weekly };
  }, [savedJobs]);
  const hasWeeklyData = chartData.weekly.some((item) => item.value > 0);
  const isLoading = jobs.isLoading;
  const hasError = jobs.isError;

  const unscoredCount = useMemo(
    () => savedJobs.filter((j) => j.match_score == null && j.score == null).length,
    [savedJobs],
  );

  const upcomingDeadlines = useMemo(
    () => savedJobs.filter((j) => j.deadline).length,
    [savedJobs],
  );

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="visible"
      className="space-y-6"
    >
      <motion.div variants={staggerItem}>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Track saved jobs, match scores, reviews, and upcoming deadlines.</p>
      </motion.div>
      {hasError ? <div className="rounded-md border border-destructive/30 p-4 text-sm text-destructive">Some dashboard data could not be loaded. Refresh or check the API connection.</div> : null}

      {isLoading ? (
        <div className="space-y-6">
          <Skeleton className="h-24 w-full rounded-lg" />
          <SkeletonKPIRow />
          <div className="grid gap-4 lg:grid-cols-2">
            <SkeletonChart />
            <SkeletonChart />
            <SkeletonChart />
          </div>
        </div>
      ) : (
        <>
          <NextBestAction
            unscoredCount={unscoredCount}
            hasProfile={false}
            hasAiProvider={false}
            totalJobs={savedJobs.length}
          />
          <motion.div variants={container} initial="hidden" animate="visible" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi label="Saved Jobs" value={savedJobs.length} icon={Briefcase} />
            <Kpi label="High Match (80+)" value={savedJobs.filter((j) => Number(j.match_score ?? j.score ?? 0) >= 80).length} icon={Sparkles} />
            <Kpi label="Need Review" value={savedJobs.filter((j) => (j.status ?? "new").includes("review")).length} icon={ClipboardCheck} />
            <Kpi label="Upcoming Deadlines" value={upcomingDeadlines} icon={CalendarClock} urgent={upcomingDeadlines > 0} />
          </motion.div>
          <motion.div variants={chartContainer} initial="hidden" animate="visible" className="grid gap-4 lg:grid-cols-2">
            <motion.div variants={staggerItem}>
              <Card><CardHeader><CardTitle>Job Sources</CardTitle></CardHeader><CardContent><SourceChart data={chartData.sources.length ? chartData.sources : [{ name: "No data", value: 1 }]} /></CardContent></Card>
            </motion.div>
            <motion.div variants={staggerItem}>
              <Card><CardHeader><CardTitle>Match Score Distribution</CardTitle></CardHeader><CardContent><ScoreDistribution data={chartData.buckets} /></CardContent></Card>
            </motion.div>
            <motion.div variants={staggerItem}>
              <Card><CardHeader><CardTitle>Weekly Activity</CardTitle></CardHeader><CardContent>{hasWeeklyData ? <TrendChart data={chartData.weekly} /> : <div className="py-12 text-center text-sm text-muted-foreground">No data available</div>}</CardContent></Card>
            </motion.div>
          </motion.div>
        </>
      )}
    </motion.div>
  );
}
