# Architecture

## Overview

The Job Assistant is a full-stack web application with:

- **Frontend**: Next.js 15 (App Router) + React 19 + TypeScript + Tailwind CSS
- **Backend**: FastAPI (Python) with modular service layer
- **Database**: MongoDB (primary datastore)
- **Cache**: Redis (optional, for rate limiting)

---

## Backend Architecture

### Structure

```
backend/
  job_assistant/
    api.py              — FastAPI router (~3200 lines, all REST endpoints)
    auth.py             — Authentication (PBKDF2, JWT, session management)
    db.py               — MongoDB data access layer (~2600 lines)
    config.py           — Pydantic settings (environment, deployment profile)
    ai_orchestrator.py  — AI provider routing, daily budget enforcement, cost tracking
    agent_chat.py       — Conversational agent (intent classification, streaming chat)
    provider_registry.py — Provider abstraction layer with fallback execution
    scheduler.py        — APScheduler-based background jobs
    worker_queue.py     — MongoDB-backed async job queue
    rate_limits.py      — ASGI middleware for per-resource rate limiting
    automation_engine.py — If/then automation rule engine
    publishing_engine.py — Draft/approve/publish content to social platforms
    compliance.py       — GDPR data export, deletion, retention
    observability.py    — Prometheus metrics, alerting
    backup.py           — Automated MongoDB backups (local + S3)
    crypto.py           — Fernet encryption for stored secrets
    email_delivery.py   — SMTP email (password reset)
    followups.py        — Auto follow-up reminders
    logging_config.py   — Structured logging
    runtime.py          — Startup validation and runtime info
    services/           — Business logic modules (see below)
```

### Services Layer

| Module | Purpose |
|--------|---------|
| `ai_providers.py` | 9 AI provider adapters (OpenAI, Azure, Claude, Gemini, Grok, Groq, HuggingFace API/Local, Ollama) |
| `openai_client.py` | Shared OpenAI-format client used by multiple providers |
| `scoring.py` | Heuristic + AI-assisted opportunity scoring (jobs, hackathons, competitions, webinars) |
| `generation.py` | Application materials generation (cover letter, resume bullets, etc.) |
| `parsing.py` | Resume text extraction (PDF/DOCX/TXT), job extraction from text/URL, CSV import |
| `resume_builder.py` | DOCX resume rendering in 6 country templates (US, UK, Europe, Canada, Australia, International) |
| `job_context.py` | Keyword/focus-area extraction for AI grounding |
| `public_discovery.py` | 7 public job board adapters with aggregation + dedup |
| `job_source_scrapers.py` | Per-user URL-driven scrapers (Indeed, Seek, LinkedIn) |
| `job_import.py` | Unified import pipeline with classification, dedup, and DB insertion |
| `opportunity_classifier.py` | Evidence-based classification of opportunity types |
| `gmail_ingest.py` | Gmail OAuth flow and job alert email fetching |
| `rapidapi_linkedin.py` | LinkedIn job search via RapidAPI |
| `apify_integration.py` | Apify actor execution for custom scraping |
| `linkedin_integration.py` | Placeholder for future official LinkedIn SDK |
| `prompt_protection.py` | Prompt injection detection and input sanitization |

### Request Flow

```
Client → FastAPI (api.py) → Auth middleware (JWT) → Rate limit middleware
  → Route handler → Service functions → MongoDB (db.py)
  → AI calls (ai_orchestrator.py → ai_providers.py)
  → Response
```

### AI Routing

```
resolve_route(user):
  1. Check provider_configs (platform="ai", active, by priority)
  2. Check integration_settings (service="ai_provider", legacy)
  3. Fallback → local heuristic (no API key required, never fails)
```

---

## Frontend Architecture

### Structure

```
frontend/src/
  app/                  — Next.js App Router
    (app)/              — Authenticated routes (dashboard, opportunities, agent, etc.)
    (auth)/             — Auth routes (login, register, forgot-password)
  components/           — Shared UI components
  features/             — Domain feature modules
    activity/           — Activity feed
    agent/              — AI chat interface
    ai/                 — AI usage/health dashboard
    analytics/          — Opportunity analytics
    auth/               — Authentication forms
    automation/         — Automation rules UI
    dashboard/          — Main dashboard
    integrations/       — Provider/integration configuration
    opportunities/      — Opportunity list + detail views
    team/               — Team management
  services/             — Typed Axios API client modules
  stores/               — Zustand stores (auth)
  types/                — TypeScript type definitions
```

### Key Routes

| Route | Feature |
|-------|---------|
| `/dashboard` | Main dashboard with summary stats |
| `/opportunities` | Job list with filters, scoring, batch operations |
| `/opportunities/[id]` | Job detail with score, materials, status |
| `/agent` | Conversational AI chat interface (SSE streaming) |
| `/ai` | AI usage dashboard (budget, cost breakdown, rate limits) |
| `/settings` | Profile, AI provider, persona, memories, prompts |
| `/integrations` | Third-party integrations (Gmail, LinkedIn, Apify) |
| `/analytics` | Opportunity analytics and trends |
| `/automation` | Automation rule management |
| `/activity` | Activity feed and audit logs |
| `/team` | Workspace members and roles |

---

## Database

### MongoDB Collections

| Collection | Purpose |
|------------|---------|
| `users` | User accounts, passwords, status |
| `profiles` | Multiple profiles per user (career data, resume text) |
| `jobs` | Opportunity records (all types) |
| `evaluations` | Match scores and component breakdown |
| `application_materials` | Generated cover letters, resume bullets, etc. |
| `applications` | Application status tracking |
| `reminders` | Manual and auto-generated reminders |
| `resume_reviews` | Tailored resume reviews |
| `interview_prep_sessions` | Generated interview prep |
| `recordings` | Practice recording metadata |
| `conversations` | Chat conversation metadata |
| `conversation_messages` | Individual chat turns |
| `agent_memory` | Cross-session user facts |
| `agent_feedback` | Thumbs up/down on messages |
| `agent_personas` | Custom agent persona settings |
| `prompt_versions` | Versioned system prompt templates |
| `ai_generations` | Log of every AI API call |
| `usage_counters` | Sliding-window rate limit counters |
| `gmail_messages` | Imported Gmail job alert messages |
| `integration_settings` | Encrypted third-party API keys |
| `provider_configs` | AI provider configurations |
| `automation_rules` | If/then automation rules |
| `automation_runs` | Automation execution history |
| `automation_errors` | Automation error logs |
| `worker_jobs` | Background job queue |
| `system_metrics` | Prometheus metrics storage |
| `alert_events` | Observability alerts |
| `audit_logs` | User action audit trail |
| `activity_events` | User activity feed |
| `feedback` | User feedback/bug reports |
| `organizations` | Multi-tenant organizations |
| `workspaces` | Workspaces within organizations |
| `workspace_members` | Member roles and status |
| `shared_resources` | Cross-workspace resource sharing |
| `posts` | Publishing engine posts |
| `post_targets` | Per-platform post targets |
| `compliance_exports` | GDPR data export records |
| `counters` | Auto-increment sequence counters |
| `password_reset_tokens` | Password reset flow |
| `user_sessions` | Refresh token sessions |
| `provider_health` | Provider health check records |

---

## External Integrations

| Integration | Type | Authentication |
|-------------|------|----------------|
| OpenAI | AI Provider | API key |
| Azure OpenAI | AI Provider | API key + endpoint |
| Anthropic Claude | AI Provider | API key |
| Google Gemini | AI Provider | API key |
| Grok (xAI) | AI Provider | API key |
| Groq | AI Provider | API key |
| Hugging Face (API) | AI Provider | API key |
| Hugging Face (Local) | AI Provider | None |
| Ollama | AI Provider | None (local) |
| RemoteJobs.org | Job Source | None (public API) |
| Arbeitnow | Job Source | None (public API) |
| Remotive | Job Source | None (public API) |
| Jobicy | Job Source | None (public API) |
| RemoteOK | Job Source | None (public API) |
| The Muse | Job Source | None (public API) |
| Hacker News | Job Source | None (public API) |
| LinkedIn (RapidAPI) | Job Source | RapidAPI key |
| Apify | Job Source | Apify API key + token |
| Gmail | Email | OAuth 2.0 |
| SMTP | Email Delivery | Username + password |
| Sentry | Error Monitoring | DSN |
| S3 (compatible) | Backup Storage | Access key + secret |
