"use client";

import Link from "next/link";
import { ArrowRight, FileText, Search, Sparkles, Settings } from "lucide-react";
import { motion } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type Action = {
  id: string;
  icon: typeof Sparkles;
  title: string;
  description: string;
  href: string;
  label: string;
  priority: number;
};

export function NextBestAction({
  unscoredCount,
  hasProfile,
  hasAiProvider,
  totalJobs,
}: {
  unscoredCount: number;
  hasProfile: boolean;
  hasAiProvider: boolean;
  totalJobs: number;
}) {
  const actions: Action[] = [];

  if (totalJobs === 0) {
    actions.push(
      { id: "find-jobs", icon: Search, title: "Find your first jobs", description: "Search public job boards or import from LinkedIn, Indeed, and more.", href: "/opportunities?source=public", label: "Find jobs", priority: 1 },
      { id: "add-profile", icon: FileText, title: "Add your resume profile", description: "Help AI match jobs to your skills and experience.", href: "/settings?tab=profile", label: "Add profile", priority: 2 },
    );
  } else if (unscoredCount > 0) {
    actions.push(
      { id: "score-jobs", icon: Sparkles, title: `${unscoredCount} job${unscoredCount > 1 ? "s" : ""} need scoring`, description: "Use AI to evaluate match scores and find your best-fit roles.", href: "/opportunities", label: "Score now", priority: 1 },
    );
  }

  if (!hasProfile) {
    actions.push(
      { id: "add-profile", icon: FileText, title: "Complete your profile", description: "A complete profile helps AI find better matches.", href: "/settings?tab=profile", label: "Set up profile", priority: totalJobs === 0 ? 3 : 2 },
    );
  }

  if (!hasAiProvider && hasProfile) {
    actions.push(
      { id: "setup-ai", icon: Settings, title: "Connect an AI provider", description: "Configure OpenAI or another provider for scoring and chat.", href: "/integrations?service=ai_provider", label: "Configure", priority: 3 },
    );
  }

  if (actions.length === 0) return null;

  const topAction = actions.sort((a, b) => a.priority - b.priority)[0];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 260, damping: 24, delay: 0.4 }}
    >
      <Card className="border-primary/20 bg-primary/[0.03]">
        <CardContent className="flex items-center justify-between gap-4 p-4 sm:p-5">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
              <topAction.icon className="h-5 w-5" />
            </span>
            <div>
              <div className="text-sm font-medium">{topAction.title}</div>
              <p className="mt-0.5 text-xs text-muted-foreground">{topAction.description}</p>
            </div>
          </div>
          <Button asChild size="sm" className="shrink-0">
            <Link href={topAction.href}>
              {topAction.label} <ArrowRight className="ml-1 h-3.5 w-3.5" />
            </Link>
          </Button>
        </CardContent>
      </Card>
    </motion.div>
  );
}
