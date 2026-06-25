# Job Assistant — Product & Architecture Guide

_Last updated: 2026-06-25_

---

## 1. What this application is

**Job Assistant is an AI-powered job-search operating system.** It takes a candidate from "I have a resume" all the way to "I applied with a tailored, country-correct resume and prepped for the interview" — and it tracks every opportunity in between.

Instead of juggling job boards, spreadsheets, a resume editor, ChatGPT tabs, and email alerts, the user works in one workspace where:

- Opportunities are **discovered** from many sources (public feeds, LinkedIn via RapidAPI, Apify scrapers, pasted text/URLs, and Gmail job alerts).
- Each opportunity is **scored** against the user's profile so they know what's worth pursuing.
- The app **generates tailored application materials** (cover letter, resume bullets, LinkedIn message, screening answers), **builds a country-standard resume document (DOCX)**, and **prepares interview questions**.
- Applications are **tracked** through a status pipeline with automatic follow-up reminders.
- A built-in **AI assistant** orchestrates all of this through chat.

It is multi-tenant (organizations → workspaces → members with role-based access), provider-agnostic on AI (OpenAI, Azure OpenAI, Claude, Gemini, Hugging Face, Ollama, or a no-key local fallback), and ships with compliance, auditing, observability, automated backups, and rate limiting built in.

---

## 2. The unique idea

Most tools do **one** slice of the job hunt — a job board, an AI resume writer, a tracker, or an autofill extension. Job Assistant's differentiator is that it closes the **entire loop in one place, grounded in the user's own profile, with a feedback loop that learns**:

1. **Profile-grounded, not generic.** Scoring, tailoring, and resume generation are all anchored to the user's structured profile and CV text — with explicit guardrails telling the AI *not to invent* employers, dates, degrees, or metrics. Output is truthful by construction.

2. **Multiple profiles → per-job targeting.** A user keeps several profiles/resumes (e.g. "Backend roles", "Platform roles") and chooses which one drives scoring and resume tailoring **for each individual job**. This is the core workflow: one identity, many targeted applications.

3. **A learning loop.** The user marks scored jobs as "relevant / not relevant," and that signal feeds back into how future jobs are scored for them — the recommendation quality improves with use.

4. **Country-aware resume building.** Resumes are rendered as real `.docx` files in the conventions of a chosen region (US, UK, Europe/Europass, Canada, Australia, International), because a CV that wins in London is formatted differently than one for the US.

5. **Provider-agnostic AI with a guaranteed floor.** Any major LLM provider can be plugged in; if none is configured or the daily budget is hit, the app degrades gracefully to local heuristics and **never breaks** — it just produces a simpler result.

6. **Built for teams, not just individuals.** The same engine runs as a personal tool or as a multi-seat, workspace-scoped product with RBAC, sharing, audit, and compliance — useful for career coaches, bootcamps, or recruiting teams.

---

## 3. Who it's for & the value delivered

| User | Value |
|------|-------|
| **Active job seekers** | Find more relevant roles faster, apply with tailored materials in minutes, never lose track of a follow-up. |
| **Career switchers** | Maintain multiple targeted profiles and see honest match scores before investing time. |
| **International applicants** | Generate resumes in the correct country format automatically. |
| **Career coaches / bootcamps / recruiting teams** | Run many candidates inside workspaces with roles, sharing, and audit. |

Concrete value: less context-switching, higher-signal targeting (scoring + learning loop), faster high-quality applications (tailored materials + resume builder), and no dropped opportunities (tracking + automatic reminders).

---

## 4. Feature catalogue

### Profile & resume intelligence
- **Multiple profiles per user** — create, name, set default, edit, delete; each is an independent resume/identity.
- **Resume import** — upload a PDF / DOCX / TXT; the app extracts text and uses AI to populate structured profile fields (skills, roles, locations, experience), which the user reviews before saving.
- **Resume builder** — generate a job-tailored, ATS-friendly resume as a downloadable `.docx` in a chosen country template (US, UK, Europe/Europass, Canada, Australia, International).
- **Resume review** — AI feedback on a resume against a target role/job (strengths, gaps, missing keywords, formatting tips).

### Opportunity discovery (multi-source)
- **Enter job details directly** — structured form with title, company, and description fields (no URL required). Runs through the same classification, dedup, and scoring pipeline as auto-discovered jobs.
- **Paste text or URL** → AI extracts a clean opportunity (handles single listings and pages with multiple nested listings).
- **Public job feeds** — RemoteJobs, Arbeitnow, Remotive, Jobicy, Hacker News, etc.
- **LinkedIn via RapidAPI**, **Apify scraper actors**, and **paginated URL import** for custom boards.
- **Find jobs from profile** — auto-builds a search from the user's skills/roles, then optionally scores and imports results.
- **Gmail ingestion** — connect Gmail, detect job-alert emails, and turn them into tracked opportunities.
- **Opportunity classifier** — distinguishes real jobs/internships/contracts from newsletters, webinars, and hackathons, and gates what gets imported.

### Scoring & matching
- **Match scoring** of each opportunity against the selected profile — overall score plus component breakdown (skills, title, seniority, location, salary, industry, work authorization, deal-breakers).
- **Per-job profile selection** — choose which profile scores/tailors a given job.
- **Batch scoring** — score selected jobs or all unscored jobs at once.
- **Relevance feedback loop** — thumbs up/down recalibrates future scoring for that user.

### Application execution & tracking
- **Application materials generation** — cover letter, resume bullets, LinkedIn outreach message, screening-question answers, "why I fit."
- **Interview prep** — behavioral, technical, role-specific, and company-specific questions plus answer outlines and a prep checklist.
- **Practice recordings** — record/upload audio answers and store them per job.
- **Application pipeline** — status tracking (New → Reviewed → Applied → Interview → Offer / Rejected → Archived) with notes.
- **Reminders & auto follow-ups** — manual reminders plus automatic follow-up reminders for stale "Applied" jobs.

### AI assistant
- **Conversational agent** (`/agent`) that classifies intent (chat, job search, resume tailoring, interview prep) using tool/function calling and routes to the appropriate handler — with **streaming (Server-Sent Events)** responses.
- **Conversation state machine** — tracks idle, searching, tailoring, interviewing, chatting states on the conversation document.
- **Follow-up suggestions** — AI-generated next-step prompts delivered as SSE events after each reply.
- **Cross-session agent memory** — key-value store (`agent_memory` collection) where facts the agent learns are persisted across conversations; auto-extracted from chat or managed manually via `?tab=memories`.
- **Feedback loop** — thumbs up/down on individual messages with persisted ratings.
- **Agent persona** — customizable assistant role, tone, and behavior via `?tab=persona`.
- **Prompt versioning** — system prompt templates stored with semantic versioning and active-version rollback via `?tab=prompts`.

### Automation & publishing
- **Automation rules** — if/then workflows (trigger event → action) with run history and error logs.
- **Publishing engine** — draft/approve/publish posts to social platforms with per-platform content validation (character/media limits).
- **Scheduler** — background polling for Gmail, discovery, and daily summaries.

### Team, governance & operations
- **Organizations → Workspaces → Members** with **RBAC** (owner/admin/manager/viewer) and fine-grained permissions.
- **Resource sharing** across a workspace.
- **Audit logs** of user actions (with IP/user-agent), **activity feed**, and **feedback/bug submission**.
- **Compliance** — GDPR-style data export, deletion request/approval, retention policies.
- **Observability** — Prometheus metrics, latency tracking, alerts; **automated SQLite backups** (with optional S3); **per-resource-type rate limiting** with sliding-window counters (Redis or MongoDB); **daily AI generation budget** with per-task-type cost breakdown.
- **Usage monitoring** — `GET /ai/usage` returns daily budget, today/week/month totals by task type, and 30-day daily history; rate-limit status endpoint `GET /rate-limits` with color-coded thresholds in the settings dashboard (`?tab=usage`).

---

## 5. Integrations

| Category | Integrations |
|----------|--------------|
| **AI / LLM providers** | OpenAI, Azure OpenAI (Chat Completions **and** Responses API for reasoning/codex models), Anthropic Claude, Google Gemini, Hugging Face (API + local), Ollama / OpenAI-compatible, and a no-key local heuristic fallback. |
| **Job sources** | Public feeds (RemoteJobs, Arbeitnow, Remotive, Jobicy, Hacker News…), LinkedIn (via RapidAPI), Apify actors, arbitrary URLs, pasted text. |
| **Email** | Gmail (OAuth) — ingest job-alert emails. |
| **Email delivery** | SMTP — password reset & notifications. |
| **Publishing** | Social platform targets (e.g. LinkedIn/Twitter) via the publishing engine. |
| **Ops** | Sentry (error monitoring), Prometheus (metrics), S3 (optional backup storage), Redis (optional, for rate limiting; SQLite fallback otherwise). |

Provider credentials are stored **encrypted at rest** and never returned to the client — the UI only shows a "key saved" indicator.

---

## 6. How it works — the user journey

```
                ┌─────────────────────────────────────────────────────────────┐
                │                     1.  SET UP IDENTITY                       │
                │   Register → workspace auto-bootstraps → create profile(s)    │
                │   Upload resume (PDF/DOCX) → AI extracts → review & save      │
                └─────────────────────────────────────────────────────────────┘
                                          │
                ┌─────────────────────────▼───────────────────────────────────┐
                │                       2.  DISCOVER                            │
                │  Find from profile · public feeds · LinkedIn/Apify · paste    │
                │  URL/text · Gmail alerts  →  classifier filters real jobs     │
                └─────────────────────────────────────────────────────────────┘
                                          │
                ┌─────────────────────────▼───────────────────────────────────┐
                │                        3.  SCORE                              │
                │  Pick a profile → AI/heuristic match score + breakdown        │
                │  Thumbs up/down  →  feedback loop tunes future scoring        │
                └─────────────────────────────────────────────────────────────┘
                                          │
                ┌─────────────────────────▼───────────────────────────────────┐
                │                    4.  APPLY (tailored)                       │
                │  Tailor resume · build DOCX (country template) · cover letter │
                │  + screening answers + LinkedIn msg · interview prep + record │
                └─────────────────────────────────────────────────────────────┘
                                          │
                ┌─────────────────────────▼───────────────────────────────────┐
                │                       5.  TRACK                               │
                │  Status pipeline · notes · reminders · auto follow-ups        │
                │  Analytics: by type/source, score distribution, trends        │
                └─────────────────────────────────────────────────────────────┘
```

The conversational **assistant** can drive steps 2–4 directly ("find me backend jobs," "tailor my resume for this role").

---

## 7. System architecture

### High-level

```
┌──────────────────────────┐         HTTPS / JSON          ┌───────────────────────────────┐
│        FRONTEND           │  ───────────────────────────► │            BACKEND             │
│  Next.js 15 (App Router)  │   Bearer token + refresh      │      FastAPI (/api/v1/*)       │
│  React 19 · TS · Tailwind │ ◄───────────────────────────  │                                │
│  TanStack Query · Zustand │      SSE (agent streaming)    │  Routers → Services → DB       │
└──────────────────────────┘                               └───────────────┬───────────────┘
                                                                            │
        ┌──────────────────────────────┬───────────────────┬───────────────┼────────────────┐
        ▼                              ▼                   ▼               ▼                ▼
 ┌─────────────┐              ┌────────────────┐   ┌──────────────┐ ┌────────────┐  ┌──────────────┐
 │ AI Orchestr.│              │ Discovery /    │   │  Scheduler / │ │  SQLite    │  │ Observability│
 │ + providers │              │ scrapers /     │   │  worker queue│ │ (data +    │  │ metrics /    │
 │ (multi-LLM) │              │ Gmail ingest   │   │  / followups │ │  queue)    │  │ alerts /     │
 └──────┬──────┘              └────────────────┘   └──────────────┘ └────────────┘  │ backups      │
        ▼                                                                            └──────────────┘
 OpenAI · Azure · Claude · Gemini · HF · Ollama · local fallback
```

### Backend (FastAPI)

- **`api.py`** — the HTTP surface: ~100+ endpoints under `/api/v1/`, grouped by domain (auth, profiles, jobs, scoring, discovery, materials, resume builder, interview prep, recordings, gmail, reminders, AI, automation, publishing, integrations/providers, admin config, team/RBAC, audit/feedback, health/observability, workers, compliance, agent chat).
- **Services layer** (`services/`):
  - `ai_orchestrator` — resolves the active provider/route, enforces the daily budget, logs every generation (provider, model, tokens, latency, status).
  - `ai_providers` — adapters for each LLM (incl. Azure's Chat Completions **and** Responses API), with JSON extraction and graceful fallback.
  - `scoring` — heuristic profile↔job matching with component scores.
  - `generation` — application-material generation.
  - `parsing` — resume text extraction (PDF/DOCX/TXT), job extraction from URL/HTML, CSV import.
  - `resume_builder` — renders structured resumes to DOCX per country template.
  - `job_context` — keyword/focus-area extraction used to ground AI prompts.
  - `public_discovery`, `job_source_scrapers`, `rapidapi_linkedin`, `apify_integration`, `job_import`, `opportunity_classifier`, `gmail_ingest` — the discovery pipeline.
- **Cross-cutting modules**: `automation_engine`, `publishing_engine`, `scheduler` (APScheduler), `followups`, `worker_queue` (SQLite-backed), `rate_limits` (Redis or SQLite), `compliance`, `backup`, `observability`, `provider_registry`, `auth` (PBKDF2 + JWT sessions), `crypto` (encrypts stored secrets), `email_delivery`, `config`, `runtime`.

### Frontend (Next.js)

- **App Router** with an authenticated `(app)` route group and an `(auth)` group.
- **Routes**: `/dashboard`, `/opportunities` (+ `/opportunities/[id]`), `/agent`, `/ai`, `/analytics`, `/automation`, `/activity`, `/team`, `/integrations`, `/settings`, `/review-queue`; auth routes `/login`, `/register`, `/forgot-password`, `/reset-password`.
- **Feature modules** under `src/features` (dashboard, opportunities, agent, ai, analytics, automation, integrations, team, settings, activity, auth).
- **Services** (`src/services`) — typed Axios layer, one module per backend domain.
- **State** — Zustand `auth-store` (user + active workspace, persisted to localStorage); TanStack Query for all server state/caching.
- **Auth flow** — access token in memory + localStorage; Axios interceptor adds `Bearer`; on `401`, a coalesced refresh hits `/auth/refresh`; failed refresh redirects to `/login`. The `(app)` layout guards every protected page and bootstraps the workspace.

### AI routing & fallback (the reliability core)

```
resolve_route(user, workspace):
   1. provider_configs (platform="ai", active, by priority)   ← newer, workspace-scoped
   2. else integration_settings (service="ai_provider")        ← simple per-user config
   3. else  →  local heuristic fallback (no key, never fails)
   ↳ daily AI budget enforced; every call logged to ai_generations
```

Every AI feature (scoring, extraction, tailoring, resume building, interview prep, chat) goes through this single path, so the app behaves consistently and always returns valid data.

---

## 8. Data model (SQLite + MongoDB)

**SQLite** stores core business data. **MongoDB** stores high-volume/transient data for the AI assistant, usage monitoring, and rate limiting.

### SQLite tables

- **Identity & tenancy**: `users`, `user_sessions`, `password_reset_tokens`, `organizations`, `workspaces`, `workspace_members`, `roles`, `permissions`, `role_permissions`, `shared_resources`.
- **Career data**: `profile` (multiple per user, one default), `jobs` (workspace-scoped, unique per user+workspace+url), `evaluations` (scores), `application_materials`, `applications` (status), `reminders`, `resume_reviews`, `interview_prep_sessions`, `recordings`.
- **Integrations & AI**: `integration_settings` (encrypted), `provider_configs`, `gmail_messages`, `prompt_versions`.
- **Automation & publishing**: `automation_rules`, `automation_runs`, `automation_errors`, `automation_preferences`, `posts`, `post_targets`.
- **Governance & ops**: `audit_logs`, `activity_events`, `feedback`, `system_metrics`, `alert_events`, `worker_jobs`, `compliance_exports`, `schema_migrations`.

### MongoDB collections

- `ai_generations` — every AI call logged with provider, model, tokens, latency, status, estimated cost, and task type.
- `agent_memory` — per-user key-value facts that the agent remembers across sessions; unique index on `(user_id, key)`, max 50 per user.
- `usage_counters` — sliding-window counters for per-resource-type rate limiting.
- `conversations` — chat conversation metadata (title, state, timestamps).
- `conversation_messages` — individual chat turns with role, content, sections, feedback.

> The data layer ships with **incremental, idempotent migrations** (e.g. the single-profile → multi-profile migration preserves existing data and marks it the default).

---

## 9. Security, privacy & reliability

- **Auth**: PBKDF2-hashed passwords, JWT access tokens, refresh-token sessions with revocation; password-reset tokens with IP/user-agent audit.
- **Secrets**: provider API keys encrypted at rest; never returned to the client (UI shows only "key saved").
- **Isolation**: every business record is workspace-scoped; RBAC + permission checks gate access.
- **Compliance**: GDPR export, deletion request/approval, retention policies.
- **Resilience**: per-IP rate limiting, daily AI budget cap, automated backups (optional S3), Prometheus metrics + alerts, Sentry error monitoring, structured logging, AI local-fallback floor.

---

## 10. Technology stack

**Backend**: Python · FastAPI · SQLite · MongoDB (PyMongo) · APScheduler · python-jose (JWT) · pypdf + python-docx · OpenAI/Azure/Anthropic/Gemini/Hugging Face/LangChain SDKs · Prometheus client · Sentry · (optional Redis, S3).

**Frontend**: Next.js 15 (App Router) · React 19 · TypeScript 5 · TanStack Query 5 · Zustand 5 · Axios · Tailwind CSS 3 · Recharts · React Hook Form + Zod · Radix UI · lucide-react · sonner · next-themes.

---

## 11. How to use it (step by step)

1. **Sign up & sign in** at `/register` then `/login`. A personal workspace is created automatically.
2. **Build your profile** — go to **Settings → Profile**. Either fill the fields manually or click **Upload resume** (PDF/DOCX/TXT); the app extracts your details — review them and **Save**. Create additional named profiles for different target roles (e.g. "Backend", "Platform") and set a default.
3. **Connect AI** (recommended) — go to **AI Provider** (`/integrations?service=ai_provider`), choose your provider (e.g. Azure OpenAI), paste the key, set model/endpoint/deployment, and Save. Without this the app still works using local heuristics.
4. **Find jobs** — use **Find Jobs** (from your profile or public feeds), connect **Gmail** to ingest alerts, or **Add Job** by pasting a URL/description.
5. **Score & triage** — open a job, pick which **profile** to score against, and run **Refresh AI score**. Use 👍/👎 to teach the system; filter the list by status/type/search.
6. **Apply** — on a job, **Tailor resume**, **Build resume (DOCX)** in your country's format, **Generate materials** (cover letter, etc.), and **Generate interview prep**. Optionally record practice answers.
7. **Track** — mark status (Applied, Interview…), add notes, and let **auto follow-up reminders** keep stale applications on your radar.
8. **Ask the assistant** — at `/agent`, chat: "find me remote backend roles," "tailor my resume for this job," "prep me for this interview."
9. **Review insights** — `/analytics` for trends; `/ai` for AI usage/health; `/activity` for audit/feedback.
10. **(Teams)** — invite members under `/team`, assign roles, and share resources within a workspace.

---

## 12. Notes & current limitations

- Default datastore is **SQLite** (a Postgres migration path exists via `scripts/sqlite_to_postgres.py`).
- `linkedin_integration` is a placeholder for a future official SDK; LinkedIn discovery today goes through **RapidAPI** / Apify.
- Azure reasoning/codex deployments (e.g. `gpt-5.x`, `*-codex`, o-series) require the **Responses API** — this is auto-detected by deployment name.
- AI quality depends on the configured provider; with no provider, features fall back to local heuristics (simpler, but functional).
