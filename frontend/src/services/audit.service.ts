import { getJson } from "@/services/client";
import type { AuditLog, DetailedUsage, RateLimitStatus } from "@/types/api";

export const auditService = {
  logs: (workspace_id?: number, limit = 100) => getJson<AuditLog[]>("/audit-logs", { workspace_id, limit }),
  usage: () => getJson<DetailedUsage>("/ai/usage"),
  rateLimits: () => getJson<RateLimitStatus>("/rate-limits"),
  observability: (hours = 24) => getJson<Record<string, unknown>>("/observability", { hours }),
  health: () => getJson<Record<string, unknown>>("/health"),
  runtime: () => getJson<Record<string, unknown>>("/health/runtime"),
  workers: () => getJson<Record<string, unknown>>("/workers/health"),
};
