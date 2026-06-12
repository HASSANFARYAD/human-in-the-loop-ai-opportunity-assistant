# Job Application Assistant

Local-first Next.js + FastAPI + SQLite assistant for collecting, scoring, reviewing, and tracking job opportunities. The app is human-in-the-loop: it helps organize and draft, but it does not submit applications, bypass platform rules, or scrape private pages.

## What It Does

- Stores user accounts, sessions, profile/resume context, provider settings, and opportunity data in SQLite.
- Imports opportunities from pasted text, CSV, configured Gmail alerts, public no-login sources, and user-configured Apify actors.
- Scores job-like opportunities against a saved profile and can draft editable materials, resume reviews, and interview prep.
- Tracks application status, notes, reminders, recordings metadata, and generated artifacts.

## Local Setup

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Frontend:

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
APP_DB_PATH=backend/data/job_assistant.sqlite3
APP_DATA_DIR=backend/data
JWT_SECRET_KEY=replace-with-a-long-random-secret
APP_ENCRYPTION_KEY=replace-with-a-fernet-key
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
CORS_ALLOW_CREDENTIALS=true
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_SAMESITE=lax
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

SQLite remains the default. On Render, SQLite requires a persistent disk and is suitable only for small or single-user deployments. Do not enable PostgreSQL unless the backend has been verified end-to-end for it.

## Premortem

- AI provider/API failures: keep fallback scoring visible, show provider errors clearly, and avoid blocking manual review.
- Fallback scoring quality: treat scores as prioritization hints, not decisions; review low-confidence matches manually.
- Bad filtering/classification: keep manual import/status controls and inspect skipped items before deleting.
- Empty or dirty database states: use `/api/v1/health`, the dry-run cleanup command, and SQLite backup/restore before destructive cleanup.
- Render persistent disk misconfiguration: set `APP_DB_PATH` under the mounted disk and confirm `/api/v1/health/storage` after deploy.
- Vercel/backend CORS or API URL issues: set `NEXT_PUBLIC_API_URL` to the Render API origin and include the exact Vercel origin in `CORS_ORIGINS`.
- Slow discovery/scoring: keep scheduler disabled on small Render instances unless needed; score in smaller batches.
- Missing resume/profile data: scoring and tailored outputs require profile context, so complete the profile before evaluating jobs.
- Poor mobile layout: test core workflows on a phone viewport before launch.
- Hidden old routes still existing: do not advertise unfinished routes; verify production navigation and build output before sharing.
