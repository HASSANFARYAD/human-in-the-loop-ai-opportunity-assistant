"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface ScoreBadgeProps {
  score: number | null;
  size?: "sm" | "md" | "lg";
  animated?: boolean;
  className?: string;
}

const sizeMap = {
  sm: { ring: 32, stroke: 3, fontSize: "text-[10px]" },
  md: { ring: 40, stroke: 3.5, fontSize: "text-xs" },
  lg: { ring: 56, stroke: 4, fontSize: "text-sm" },
};

function scoreColor(score: number | null) {
  if (score == null) return "text-muted-foreground";
  if (score >= 90) return "text-success";
  if (score >= 70) return "text-primary";
  if (score >= 50) return "text-warning";
  return "text-destructive";
}

function scoreRingColor(score: number | null) {
  if (score == null) return "stroke-muted-foreground/30";
  if (score >= 90) return "stroke-success";
  if (score >= 70) return "stroke-primary";
  if (score >= 50) return "stroke-warning";
  return "stroke-destructive";
}

export function ScoreBadge({ score, size = "md", animated = true, className }: ScoreBadgeProps) {
  const [displayScore, setDisplayScore] = useState(animated ? 0 : (score ?? 0));
  const dims = sizeMap[size];
  const radius = (dims.ring - dims.stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = score != null ? circumference * (1 - Math.min(score, 100) / 100) : circumference;

  useEffect(() => {
    if (!animated || score == null) {
      setDisplayScore(score ?? 0);
      return;
    }
    const duration = 800;
    const steps = 30;
    const increment = (score - displayScore) / steps;
    let step = 0;
    const timer = setInterval(() => {
      step++;
      setDisplayScore((prev) => Math.min(Math.round(prev + increment), score));
      if (step >= steps) {
        setDisplayScore(score);
        clearInterval(timer);
      }
    }, duration / steps);
    return () => clearInterval(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [score]);

  if (score == null) {
    return (
      <span className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium text-muted-foreground", className)}>
        —
      </span>
    );
  }

  return (
    <motion.span
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 20 }}
      className={cn("inline-flex items-center gap-1", className)}
      title={`${score}% match`}
    >
      <svg width={dims.ring} height={dims.ring} className="shrink-0">
        <circle
          cx={dims.ring / 2}
          cy={dims.ring / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={dims.stroke}
          className="text-muted/40"
        />
        <motion.circle
          cx={dims.ring / 2}
          cy={dims.ring / 2}
          r={radius}
          fill="none"
          strokeWidth={dims.stroke}
          strokeLinecap="round"
          className={scoreRingColor(score)}
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1, ease: "easeOut" }}
          transform={`rotate(-90 ${dims.ring / 2} ${dims.ring / 2})`}
        />
        <text
          x="50%"
          y="50%"
          textAnchor="middle"
          dominantBaseline="central"
          className={cn("font-semibold tabular-nums fill-current", scoreColor(score), dims.fontSize)}
        >
          {displayScore}
        </text>
      </svg>
    </motion.span>
  );
}
