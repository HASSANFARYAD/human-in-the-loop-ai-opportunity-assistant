import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(value?: string | null) {
  if (!value) return "Not set";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

export function scoreTone(score?: number | null) {
  const normalized = Number(score ?? 0);
  if (normalized >= 80) return "text-success";
  if (normalized >= 60) return "text-warning";
  return "text-muted-foreground";
}
