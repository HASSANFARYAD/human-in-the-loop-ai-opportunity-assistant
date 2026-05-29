export type ApiList<T> = T[];

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
  status?: string;
  notes?: string;
  created_at?: string;
  updated_at?: string;
  match_score?: number | null;
  score?: number | null;
  evaluation?: Record<string, unknown> | null;
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

export interface Integration {
  service: string;
  has_api_key: boolean;
  config: Record<string, unknown>;
  updated_at?: string;
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
