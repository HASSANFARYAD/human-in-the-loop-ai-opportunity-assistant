export type ApiList<T> = T[];
export type OpportunityContentType = "job" | "all" | "internship" | "contract" | "freelance";

export interface User {
  id: number;
  email: string;
  full_name?: string;
  role?: string;
  created_at?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export interface Opportunity {
  id: number;
  workspace_id?: number | null;
  title: string;
  company?: string | null;
  location?: string | null;
  remote_type?: string | null;
  url?: string | null;
  source: string;
  description?: string;
  salary_min?: number | null;
  salary_max?: number | null;
  deadline?: string | null;
  opportunity_type?: string;
  classification?: string;
  classification_reason?: string;
  classification_confidence?: number | null;
  opportunity_confidence?: number | null;
  importable?: boolean | number;
  blocked_reason?: string;
  extracted_opportunities_count?: number;
  source_type?: string;
  source_name?: string;
  source_url?: string;
  source_email_id?: string;
  source_email_open_url?: string;
  parent_source_id?: string;
  parent_source_title?: string;
  extracted_from?: string;
  raw_source_snippet?: string;
  original_url?: string;
  resolved_url?: string;
  status?: string;
  notes?: string;
  created_at?: string;
  updated_at?: string;
  match_score?: number | null;
  score?: number | null;
  evaluation?: Record<string, unknown> | null;
}

export interface BatchScoreResultItem {
  job_id: number;
  title?: string;
  status: "success" | "skipped" | "failed" | string;
  classification?: string;
  reason?: string;
  error?: string;
  evaluation?: Record<string, unknown>;
}

export interface BatchScoreResult {
  status: string;
  total: number;
  total_requested?: number;
  succeeded: number;
  scored?: number;
  skipped: number;
  failed: number;
  using_fallback_scoring?: boolean;
  results: BatchScoreResultItem[];
}

export interface TailoredResume {
  id?: number;
  job_id?: number;
  type?: string;
  target_role?: string;
  company?: string;
  tailored_summary?: string;
  tailored_experience_bullets?: string[];
  skills_to_emphasize?: string[];
  keywords_to_include?: string[];
  optional_cover_note?: string;
  application_guidance?: string[];
  resume_draft?: string;
  generation_source?: string;
  using_fallback?: boolean;
  ai_error?: string;
  created_at?: string;
}

export interface ProfileJobDiscoveryResult {
  status: string;
  query: string;
  keywords: string[];
  opportunities: Opportunity[];
  found: number;
  imported: number;
  ids?: number[];
  scored: number;
  using_fallback_scoring?: boolean;
  warnings?: string[];
  errors?: string[];
  message?: string;
}

export interface Profile {
  id?: number;
  name?: string;
  is_default?: number;
  cv_text?: string;
  target_roles?: string;
  industries?: string;
  locations?: string;
  remote_preference?: string;
  salary_expectations?: string;
  work_authorization?: string;
  years_experience?: string;
  skills?: string;
  deal_breakers?: string;
  full_name?: string;
  email?: string;
  preferred_role?: string;
  country?: string;
  job_preferences?: string;
  platforms?: string;
  resume_name?: string;
  integration_status?: string;
}

export interface Workspace {
  id: number;
  organization_id?: number;
  name: string;
  description?: string;
  role?: string;
  created_at?: string;
}

export interface AutomationRule {
  id: number;
  name: string;
  trigger_event: string;
  action_type: string;
  is_active: boolean;
  human_approval_required?: boolean;
  created_at?: string;
}

export interface AutomationRun {
  id: number;
  rule_id?: number;
  status: string;
  trigger_event?: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

export interface ProviderConfig {
  id?: number;
  platform: string;
  provider_name: string;
  auth_type?: string;
  priority?: number;
  is_active?: boolean;
  has_credentials?: boolean;
  config?: Record<string, unknown>;
  updated_at?: string;
}

export interface Conversation {
  id: number;
  conversation_id: number;
  user_id: number;
  workspace_id?: number | null;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: number;
  conversation_id: number;
  role: "user" | "assistant";
  content: string;
  sections: AgentSection[];
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ConversationMessage[];
}

export interface AgentJobListing {
  title: string;
  company: string;
  location: string;
  url: string;
  source: string;
  opportunity_type: string;
  match_score: number;
  priority: string;
  good_fit: string;
}

export interface AgentSection {
  agent: "job_search" | "tailor_resume" | "interview_prep" | "chat";
  type: "listings" | "tailored_resume" | "interview_prep" | "message" | "error";
  message?: string;
  data?: unknown;
  job?: { id: number; title?: string; company?: string };
  suggestions?: string[];
}

export interface AgentPersona {
  tone: "professional" | "friendly" | "casual";
  detail_level: "concise" | "balanced" | "thorough";
  focus_area: "general" | "technical" | "managerial";
}

export interface AgentMemory {
  id: number;
  key: string;
  value: string;
  source: "manual" | "extracted";
  created_at: string;
  updated_at: string;
}

export interface PromptVersion {
  id?: number;
  name: string;
  version: string;
  template: string;
  description?: string;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface AgentChatResponse {
  intents: string[];
  sections: AgentSection[];
}

export interface AIUsageBudget {
  used: number;
  limit: number;
  remaining: number | null;
  unlimited: boolean;
}

export interface UsageTaskType {
  task_type: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  avg_latency_ms: number;
}

export interface UsagePeriodTotal {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
}

export interface UsagePeriod {
  total: UsagePeriodTotal;
  by_task_type: UsageTaskType[];
}

export interface UsageDailyEntry {
  date: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  failed: number;
}

export interface DetailedUsage {
  budget: AIUsageBudget;
  today: UsagePeriod;
  this_week: UsagePeriod;
  this_month: UsagePeriod;
  daily_history: UsageDailyEntry[];
}

export interface RateLimitEntry {
  resource_type: string;
  limit: number;
  used: number;
  remaining: number;
  window_start: string;
  window_end: string;
}

export interface RateLimitStatus {
  rate_limits: RateLimitEntry[];
}

export interface AIUsage {
  used: number;
  limit: number;
  remaining: number | null;
  unlimited: boolean;
}

export interface Integration {
  service: string;
  has_api_key: boolean;
  config: Record<string, unknown>;
  updated_at?: string;
}

export interface AdminConfig {
  id: string | number;
  type: "ai_provider" | "gmail" | "recording_storage";
  name: string;
  display_name?: string;
  is_active: boolean;
  has_secret: boolean;
  secret_label?: string;
  config: Record<string, unknown>;
  updated_at?: string;
  source?: string;
  priority?: number;
}

export interface AdminConfigStatus {
  type: string;
  status: "configured" | "inactive" | "missing";
  configured: boolean;
  count: number;
  active_count: number;
}

export interface AuditLog {
  id: number;
  action: string;
  resource_type?: string;
  resource_id?: string;
  created_at?: string;
  metadata?: Record<string, unknown>;
}

export interface Feedback {
  id: number;
  category: string;
  title: string;
  description: string;
  severity: string;
  status?: string;
  created_at?: string;
}

export interface WorkspaceMember {
  id: number;
  user_id: number;
  workspace_id: number;
  role: string;
  email?: string;
  full_name?: string;
  joined_at?: string;
}

export interface Role {
  id: number;
  name: string;
  description?: string;
  permissions?: string[];
}

export interface AIGeneration {
  id: number;
  provider?: string;
  model?: string;
  task_type?: string;
  status?: string;
  input_tokens?: number;
  output_tokens?: number;
  estimated_cost?: number;
  latency_ms?: number;
  error_message?: string;
  created_at?: string;
}

export interface AIPrompt {
  id: number;
  name: string;
  version: string;
  description?: string;
  is_active?: boolean;
  created_at?: string;
}

export interface Reminder {
  id: number;
  job_id?: number;
  title?: string;
  note?: string;
  due_at?: string;
  status?: string;
  created_at?: string;
}

export interface Loop {
  id: number;
  loop_id: number;
  name: string;
  search_query: string;
  sources: string[];
  platforms: string[];
  is_active: boolean;
  auto_apply_enabled: boolean;
  daily_budget: number;
  max_applications_per_run: number;
  min_score_threshold: number;
  channels: string[];
  schedule_interval_hours: number;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LoopRun {
  id: number;
  loop_run_id: number;
  loop_id: number;
  status: string;
  jobs_discovered: number;
  jobs_qualified: number;
  applications_sent: number;
  applications_failed: number;
  budget_consumed: number;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
}

export interface AutoApplyLog {
  id: number;
  auto_apply_log_id: number;
  job_id: number;
  channel: string;
  status: string;
  score: number | null;
  error_message: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface LoopStatus {
  loop: Loop;
  daily_usage: number;
  daily_budget: number;
  budget_remaining: number;
  recent_runs: LoopRun[];
}

export interface AutoApplyStats {
  total: number;
  submitted: number;
  failed: number;
  skipped: number;
  pending: number;
  needs_approval: number;
  budget_exceeded: number;
  period_days: number;
}

export interface AutoApplyHealth {
  status: string;
  timestamp: string;
  warnings: string[];
  circuit_breaker: {
    total_sources: number;
    open: number;
    degraded: number;
    open_sources: { source: string; cooldown_remaining_s: number }[];
    degraded_sources: { source: string; failures: number }[];
  };
  loops: {
    total: number;
    active: number;
    today_budget: number;
    today_usage: number;
    budget_remaining: number;
  };
  runs: {
    total_last_7d: number;
    success: number;
    failed: number;
    errors: number;
    success_rate_pct: number;
  };
  auto_apply: {
    applications_today: number;
    stats_7d: AutoApplyStats;
  };
}

export interface Recording {
  id: number;
  job_id?: number;
  title?: string;
  mime_type?: string;
  data_url?: string;
  playback_url?: string;
  duration_ms?: number;
  created_at?: string;
}
