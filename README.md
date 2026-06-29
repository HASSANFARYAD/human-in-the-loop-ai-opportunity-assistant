# Job Application Assistant

Next.js + FastAPI + MongoDB assistant for collecting, scoring, reviewing, and tracking job opportunities. The app is human-in-the-loop: it helps organize and draft, but it does not submit applications, bypass platform rules, or scrape private pages.

## What It Does

- Stores user accounts, sessions, profile/resume context, provider settings, and opportunity data in **MongoDB**.
- Imports opportunities from pasted text, CSV, configured Gmail alerts, public no-login sources, user-configured Apify actors, and a structured manual-entry form (title + company + description).
- Scores job-like opportunities against a saved profile and can draft editable materials, resume reviews, and interview prep.
- Tracks application status, notes, reminders, recordings metadata, and generated artifacts.
- **Conversational AI agent** with streaming chat, tool-calling intent classification, follow-up suggestions, and **cross-session agent memory** that recalls user facts across conversations.
- **Usage monitoring dashboard** with per-task-type AI cost breakdown, daily budget enforcement, and rate-limit status.
- **Multi-tenant** with organizations, workspaces, role-based access control (RBAC), and resource sharing.

## Local Setup

Requires **MongoDB** (primary datastore for all business data, agent memory, rate-limit counters, AI generation logs) and optionally **Redis** (rate-limit backend).

### MongoDB

```bash
# macOS
brew install mongodb-community
brew services start mongodb-community

# Or use Docker
docker run -d -p 27017:27017 --name mongodb mongo:7
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn api_server:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The API health endpoint is `http://localhost:8000/api/v1/health`.

## Environment Variables

Backend essentials:

```bash
ENVIRONMENT=dev
DEPLOYMENT_PROFILE=local
APP_DATA_DIR=backend/data
JWT_SECRET_KEY=replace-with-a-long-random-secret
APP_ENCRYPTION_KEY=replace-with-a-fernet-key
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
CORS_ALLOW_CREDENTIALS=true
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_SAMESITE=lax

# MongoDB (required — primary datastore)
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=career_assistant
```

Frontend essentials:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Provider/API keys are configured per user in the app where supported. Keep app-level secrets in environment variables, not in source.

## Safe Database Cleanup

The cleanup command is explicit and dry-run by default:

```bash
cd backend
python scripts/clear_jobs.py
```

To clear all job/opportunity data:

```bash
cd backend
python scripts/clear_jobs.py --confirm
```

To clear one user only:

```bash
cd backend
python scripts/clear_jobs.py --user-id 1 --confirm
```

It deletes evaluations, application materials, applications/statuses, reminders, resume reviews/tailored resumes, interview prep, recordings metadata, and jobs. It preserves users, profile/resume data, auth/session data, provider/API settings, automation preferences, app config, organizations, workspaces, and members.

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for Render backend and Vercel frontend setup.

MongoDB is the sole datastore. On Render, use MongoDB Atlas (free M0 tier) or a self-hosted instance.

## Key Features

### Conversational AI Agent (`/agent`)
- **Streaming chat** — token-by-token SSE responses with markdown rendering.
- **Intent classification** — tool-calling extracts intents (chat, job search, resume tailoring, interview prep).
- **Conversation state machine** — tracks idle, searching, tailoring, interviewing, chatting states.
- **Follow-up suggestions** — AI-generated next-step prompts after each reply.
- **Cross-session agent memory** — the agent remembers user facts across conversations (key-value store with auto-extraction and manual management).
- **System prompt versioning** — prompt templates stored in DB with active version rollback.
- **Agent persona** — customizable assistant behavior and tone.
- **Feedback** — thumbs up/down on individual messages to tune agent quality.

### Usage & Rate-Limit Monitoring
- **Per-provider cost tracking** — pricing table for 25+ models across OpenAI, Claude, Gemini, Grok, and Groq.
- **Usage dashboard** (`/settings?tab=usage`) — daily budget bar, today/week/month breakdown by task type, 30-day daily history, AI generation log.
- **Rate-limit status** — per-resource-type sliding-window counters with color-coded thresholds.
- **Daily AI budget cap** — configurable limit; soft-blocked once exhausted.

### Deduplication

Every job entry point (auto-discovery, manual import, scraper sources) runs a four-key dedup pipeline before inserting:

1. **URL** — exact match on `job_url` catches the same listing revisited.
2. **Content hash** — SHA-256 of `lowercase(strip(title|company|description))` catches the same job posted on different boards with different URLs.
3. **Title + company** — exact match on the normalized pair catches re-posted jobs with new URLs and dates.
4. **Fuzzy title+company** — `SequenceMatcher`-based fuzzy matching normalizes abbreviations (e.g. "Sr." → "Senior") and catches near-duplicates.

A match on any key rejects insertion. Within a single batch, the same in-memory checks prevent importing the same item twice.

### Human-in-the-Loop Design
- Scores are prioritization hints, not decisions — the user always reviews before acting.
- Manual import and status controls complement automated discovery.
- AI never invents employers, dates, degrees, or metrics — grounded in the user's profile.

---

## Future Goals

- **Voice input** — record audio questions in the chat UI and transcribe via Whisper or the configured AI provider.
- **Multi-branch conversations** — fork a chat at any point to explore alternative approaches without losing context.
- **Export / share conversations** — download chat transcripts as PDF or Markdown; share via link.
- **Conversation search** — full-text search across all past conversations and messages.
- **Agent tool plugins** — allow the assistant to invoke external APIs (calendar, email drafts, job board APIs) via a plugin system.
- **Automated job applications** — supervised one-click apply where the assistant fills forms and the user reviews before submission.
- **Mobile app** — React Native or Expo wrapper for the existing API surface with offline resume storage.
- **Multi-language resume generation** — produce CVs in additional languages beyond English with per-country conventions.

---

## Premortem

- AI provider/API failures: keep fallback scoring visible, show provider errors clearly, and avoid blocking manual review.
- Fallback scoring quality: treat scores as prioritization hints, not decisions; review low-confidence matches manually.
- Bad filtering/classification: keep manual import/status controls and inspect skipped items before deleting.
- Empty or dirty database states: use `/api/v1/health`, the dry-run cleanup command, and the backup scheduler before destructive cleanup.
- Render persistent disk misconfiguration: confirm MongoDB is accessible and `/api/v1/health/storage` is ok after deploy.
- Vercel/backend CORS or API URL issues: set `NEXT_PUBLIC_API_URL` to the Render API origin and include the exact Vercel origin in `CORS_ORIGINS`.
- Slow discovery/scoring: keep scheduler disabled on small Render instances unless needed; score in smaller batches.
- Missing resume/profile data: scoring and tailored outputs require profile context, so complete the profile before evaluating jobs.
- Poor mobile layout: test core workflows on a phone viewport before launch.
- Hidden old routes still existing: do not advertise unfinished routes; verify production navigation and build output before sharing.
