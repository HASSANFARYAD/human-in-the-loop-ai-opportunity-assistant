# Human-in-the-loop AI Opportunity Assistant

A local-first Streamlit + SQLite assistant for discovering, scoring, reviewing, and tracking opportunities such as jobs, hackathons, competitions, webinars, and related events.

The app is intentionally human-in-the-loop. It helps you find and prioritize opportunities, but it does not apply, register, submit forms, scrape private sites, or bypass platform rules.

## What It Does

- Stores your profile, CV text, target roles, skills, preferences, and deal-breakers locally.
- Ingests opportunities manually from pasted text or URLs.
- Imports opportunities from CSV.
- Fetches Gmail alerts through read-only OAuth when configured.
- Discovers public jobs from no-login structured sources.
- Scores jobs, hackathons, competitions, and webinars against your profile.
- Generates editable job application materials for job opportunities.
- Tracks statuses, notes, deadlines, and reminders.
- Runs optional scheduler jobs for Gmail alerts, public source discovery, reminders, and daily summaries.
- Supports separate user accounts so each user only sees and deletes their own data.

## Safety Boundary

This app does not:

- log in to LinkedIn, Indeed, Devpost, or other third-party sites
- scrape private pages
- bypass access controls
- auto-click apply/register buttons
- submit applications or hackathon registrations
- modify Gmail
- directly scrape Indeed or Devpost by default

This app does:

- use public no-auth APIs where available
- read Gmail alerts only after you configure read-only OAuth
- let you paste public opportunity text manually
- open URLs so you can review and act yourself

## Supported Opportunity Types

- `job`
- `hackathon`
- `competition`
- `webinar`
- `other`

## Public Discovery Sources

The `Public discovery` tab currently supports:

- RemoteJobs.org
- Arbeitnow
- Remotive
- Jobicy
- Hacker News Who is hiring

These sources are used because they expose structured public APIs or feeds. Direct scraping of sources like Indeed or Devpost is intentionally avoided unless an official/allowed API or feed is available.

## LinkedIn And Apify Integrations

The `Integrations` page supports user-owned credentials:

- LinkedIn official API posting
- Apify actor-based job scraping

LinkedIn posting requires your own LinkedIn OAuth access token and an author URN such as:

```text
urn:li:person:...
urn:li:organization:...
```

Your LinkedIn app/token must have the required posting scope, such as `w_member_social` for member posts. This app uses LinkedIn's official Posts API for publishing text posts. It does not use LinkedIn cookies, private endpoints, or browser automation.

Apify scraping requires:

- your Apify API token
- an actor id
- an input JSON template

Default Apify input template:

```json
{
  "startUrls": [{"url": "{{url}}"}]
}
```

Different Apify actors use different input schemas. Update the template to match the actor you choose. The app runs the actor, previews mapped job results, and imports them only after you click `Import Apify jobs`.

Use Apify actors only for sources where you have the right to collect the data and where the actor's behavior complies with the source terms.

## App Workflow

1. Register or log in.
2. Open `Profile` and save your CV, skills, roles, locations, and preferences.
3. Open `Ingest Opportunities`.
4. Use one of the ingest methods:
   - `Manual / pasted`: paste a job, hackathon, webinar, competition, or URL text.
   - `Public discovery`: search public job APIs by keyword.
   - `Apify scraper`: run your configured Apify actor against a URL.
   - `CSV upload`: import structured opportunity lists.
   - `Gmail read-only`: import matching alert emails after OAuth setup.
5. Open `Review Queue`.
6. Click `Score all unscored opportunities`.
7. Open `Opportunity Detail` to inspect scoring, update status, add notes, and generate job materials.
8. Use `Reminders` for follow-ups, deadlines, interview dates, event dates, and registration deadlines.

## Authentication And User Data

Streamlit requires users to register or log in before using the app.

Existing single-user data is migrated to a default local account:

```text
Email: local@example.com
Password: ChangeMe123!
```

Set `LOCAL_USER_PASSWORD` before migration if you want a different default password.

FastAPI exposes:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

Protected API endpoints require a bearer token:

```text
Authorization: Bearer <access_token>
```

Data is scoped by `user_id`. Profiles, opportunities, evaluations, materials, applications, and reminders are only returned for the signed-in user.

The privacy delete action is user-scoped. `Delete my stored data` removes only the signed-in user's profile, opportunities, evaluations, materials, statuses, and reminders. It does not delete other users' data.

## Automatic Mode

The sidebar has `Automatic import` controls.

When you click `Start`, the scheduler runs inside the Streamlit process:

- Gmail alerts every 30 minutes
- public job discovery every 6 hours
- due reminder checks every 5 minutes
- daily summary log at 8 AM

Automatic mode is limited to configured Gmail alerts and supported public APIs. It does not search every website on the internet and does not scrape restricted platforms.

The FastAPI server also starts the scheduler when `SCHEDULER_ENABLED=true`.

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local `.env` file for app-level configuration only:

```bash
APP_DB_PATH=data/job_assistant.sqlite3
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_TOKEN_FILE=token.json
SCHEDULER_ENABLED=true
JWT_SECRET_KEY=replace-this-with-a-long-random-secret
LOCAL_USER_PASSWORD=replace-default-local-password
APP_ENCRYPTION_KEY=replace-with-fernet-key-in-production
```

Provider API keys are not configured globally in `.env`. Each signed-in user adds their own AI, LinkedIn, RapidAPI, Apify, and other provider keys from the `Integrations` page. Those keys are encrypted and stored per user in the SQLite database. If a user has not configured an AI provider key, the app still runs with local rule-based scoring and fallback draft generation.

## Run The Streamlit App

```bash
streamlit run app.py
```

## Run The FastAPI Server

```bash
uvicorn api_server:app --reload
```

Development API docs are available at:

```text
http://localhost:8000/api/docs
```

## Gmail Read-only Setup

Gmail import requires OAuth credentials.

1. Create a Google Cloud project.
2. Enable the Gmail API.
3. Create OAuth client credentials for a Desktop app.
4. Download the file as `credentials.json` into the project root.
5. Keep `credentials.json` and `token.json` private.
6. Open `Ingest Opportunities` -> `Gmail read-only`.
7. Click `Fetch Gmail alerts`.

The app uses this scope:

```text
https://www.googleapis.com/auth/gmail.readonly
```

Default Gmail query:

```text
("job alert" OR "new jobs" OR recruiter OR "is hiring" OR hackathon OR webinar OR competition OR contest OR challenge) newer_than:30d
```

## CSV Import

Expected columns include:

- `title`
- `company`
- `location`
- `remote_type`
- `url`
- `source`
- `description`
- `salary_min`
- `salary_max`
- `deadline`
- `opportunity_type`

Extra columns are ignored.

## Data Storage

The app stores data locally in SQLite.

Default database:

```text
data/job_assistant.sqlite3
```

Main tables:

- `users`
- `profile`
- `jobs`
- `evaluations`
- `application_materials`
- `applications`
- `reminders`

The `jobs` table stores all opportunity types, not only jobs.

## Production Readiness

This is still an MVP, but user-level data isolation is now implemented.

Known production gaps:

- permissive CORS in development config
- SQLite/local file storage
- local OAuth token handling
- scheduler logs reminders but does not send push/email notifications
- limited automated test coverage
- default `JWT_SECRET_KEY` must be replaced before deployment

Before production use, harden configuration, use managed database/storage, replace all deployment secrets, add proper notification delivery, tests, monitoring, and rate limiting.

## Notes On Source Compliance

Public web pages can be visible without login but still disallow automated scraping. This app favors public APIs, feeds, Gmail alerts, CSV import, and manual paste to keep the workflow stable and respectful of source rules.

## Verify

Basic syntax check:

```bash
python -m compileall app.py job_assistant
```

## Production automation, security, sessions, and AI providers

This version includes these production-readiness upgrades:

### Encrypted secrets at rest

User API keys and integration configs are encrypted before being written to `integration_settings` using Fernet authenticated encryption. Provider keys are resolved from the signed-in user's database row, not from shared environment variables.

Generate a production encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Then set it in your environment:

```bash
APP_ENCRYPTION_KEY=your-generated-fernet-key
JWT_SECRET_KEY=your-long-random-jwt-secret
SESSION_COOKIE_SECURE=true
ENVIRONMENT=prod
```

Do not rotate `APP_ENCRYPTION_KEY` without re-encrypting existing rows, or previously stored keys will no longer decrypt.

### Persistent login

Streamlit now stores a long-lived opaque refresh/session token in a browser cookie and keeps the short-lived JWT in memory. Refresh/session tokens are hashed in the database, can be revoked on logout, and are not the same as access tokens.

For production, serve the app behind HTTPS and set:

```bash
SESSION_COOKIE_SECURE=true
REFRESH_TOKEN_EXPIRE_DAYS=30
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

### Multi-provider AI

The Integrations page now includes an AI Provider tab. Users can choose:

- OpenAI-compatible providers
- Azure OpenAI / Azure Foundry deployments
- Grok / xAI
- Anthropic Claude
- Google Gemini
- Hugging Face Inference endpoints

The selected provider is used for resume extraction, opportunity extraction, scoring, and application-material generation for that signed-in user. If no provider key is configured for that user, the app returns safe fallback data instead of failing.

### Automation preferences and progress updates

The new Automation page lets each user enable scheduled workflows, configure intervals, decide whether to score new opportunities, and optionally generate materials for high-match jobs. Scheduler runs now write progress updates to `activity_events`, which are shown in the app.

Automation still respects the original safety boundary: the app imports/organizes/scorers/generates drafts, but it does not automatically submit job applications or scrape private pages.

## Gmail integration: user flow and production notes

Current implementation uses Gmail read-only OAuth for importing job-alert emails. The app searches Gmail for job-related alerts, recruiter messages, hackathons, webinars, contests, and challenges, then converts each matching email into an opportunity.

### Local/development flow

1. In Google Cloud Console, create a project and enable the Gmail API.
2. Create OAuth client credentials for a Desktop app.
3. Download the credentials file as `credentials.json` and place it in the project root.
4. Start the app and go to `Ingest Opportunities -> Gmail read-only`.
5. Click `Fetch Gmail alerts` once. Google will open a consent flow.
6. After approval, the app stores `token.json` locally and can refresh Gmail access automatically.
7. Enable `Automation -> Import Gmail alerts automatically` and start the scheduler.

The Gmail scope is intentionally read-only:

```text
https://www.googleapis.com/auth/gmail.readonly
```

### Production recommendation

For a multi-user SaaS product, replace the local desktop OAuth flow with a web OAuth callback. Store each user's Google refresh token encrypted in `integration_settings`, never in a shared `token.json` file. The scheduler should then load the encrypted token for the active user, refresh it server-side, and run the Gmail import for that user only.

## LinkedIn post assistance

The AI does not need to post automatically to be useful. It can generate:

- a professional LinkedIn post about the user's job search,
- a role-specific networking/recruiter message,
- a short application follow-up message,
- a post announcing availability or portfolio work,
- a tailored message for each high-match opportunity.

The app currently generates a short `linkedin_message` in application materials. The `LinkedIn posting` integration can publish a text post with the user's official LinkedIn OAuth access token and author URN. For production, keep a human approval step before publishing so the user reviews the AI-generated text before it goes live.

## Automated LinkedIn job API search

The app now supports scheduled LinkedIn API imports through the configured RapidAPI LinkedIn job-search integration.

1. Go to `Integrations -> RapidAPI LinkedIn jobs`.
2. Add the RapidAPI key, host, endpoint, default title/search filter, default location filter, and number of offsets per scheduled run.
3. Go to `Automation`.
4. Enable `Search LinkedIn jobs API automatically`.
5. Set `LinkedIn API interval hours`.
6. Start the scheduler.

On each scheduled run, the app calls the configured LinkedIn jobs API, maps returned items into opportunities, scores them if scoring is enabled, optionally generates materials for high-match jobs, and writes progress to the activity feed.

## Multi-user Gmail OAuth

The app now supports Gmail for multiple users. The old `token.json` approach is only a local-development fallback and should not be used for production SaaS because it represents a single shared mailbox.

Production flow:

1. Create a Google Cloud OAuth **Web application** client.
2. Enable the Gmail API.
3. Add the app URL as an authorized redirect URI. For local Streamlit this is usually:

   ```text
   http://localhost:8501
   ```

   In production this should be your public app URL, for example:

   ```text
   https://your-domain.com
   ```

4. Configure environment variables:

   ```bash
   APP_BASE_URL=https://your-domain.com
   GOOGLE_CLIENT_ID=your-google-oauth-client-id
   GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret
   ```

5. Each logged-in user goes to `Ingest Opportunities -> Gmail read-only` and clicks **Connect Gmail**.
6. The returned Google OAuth refresh token is stored encrypted under that user's `integration_settings` row.
7. The scheduler calls Gmail with the logged-in user's own encrypted credentials, so every user imports job alerts from their own Gmail account.

Security notes:

- Gmail uses the read-only scope: `https://www.googleapis.com/auth/gmail.readonly`.
- OAuth tokens are encrypted at rest using `APP_ENCRYPTION_KEY`.
- Tokens are refreshed server-side and never exposed in the UI.
- Users can disconnect Gmail from the Gmail tab, which removes their stored Gmail credentials.

## Technical Plan Implementation Status

This build starts the MVP-to-production technical plan while preserving the current lightweight Streamlit + FastAPI + SQLite architecture.

Implemented foundations:

- per-user encrypted integration key storage in the database
- user-owned AI/provider credentials instead of shared environment keys
- feedback database table and service functions
- in-app Feedback page and sidebar quick feedback form
- FastAPI feedback endpoints
- user-scoped audit log table and audit log viewer
- database health endpoint
- storage and AI health endpoints
- local SQLite-backed API rate limiting
- provider configuration health endpoint
- Dockerfile for FastAPI
- Dockerfile.streamlit for the Streamlit UI
- docker-compose.yml with persistent SQLite/log volumes
- .dockerignore and expanded .env.example

New FastAPI endpoints:

```text
GET  /api/v1/health
GET  /api/v1/health/db
GET  /api/v1/health/storage
GET  /api/v1/health/ai
GET  /api/v1/health/providers
GET  /api/v1/usage
POST /api/v1/feedback
GET  /api/v1/feedback
GET  /api/v1/feedback/{feedback_id}
PATCH /api/v1/feedback/{feedback_id}/status
GET  /api/v1/audit-logs
```

## Docker Run

Copy the environment template and set production secrets before deploying:

```bash
cp .env.example .env
```

Run locally with Docker Compose:

```bash
docker compose up --build
```

Services:

```text
FastAPI:   http://localhost:8000
Streamlit: http://localhost:8501
```

SQLite data is persisted in the `app_data` Docker volume.

## Feedback System

Users can submit feedback from:

- the sidebar quick feedback form
- the dedicated `Feedback` page
- the FastAPI `/api/v1/feedback` endpoint

Feedback categories include bug reports, feature requests, AI quality issues, UI/UX feedback, provider/API problems, performance issues, security concerns, automation failures, integration requests, and general suggestions.

## Audit Logging

The first audit events now cover:

- feedback creation
- feedback status updates
- integration upserts
- integration deletion

The `Feedback` page shows the signed-in user's recent audit activity. Additional audit events should be added as more production features are implemented.

---

## Phase 2 Implementation Status — Deployment Readiness

Phase 2 adds the production-lite deployment foundation while keeping the MVP SQLite-first architecture intact.

### Added in Phase 2

- Deployment profiles via `DEPLOYMENT_PROFILE`:
  - `local`
  - `mvp`
  - `self_hosted`
  - `staging`
  - `production`
- Centralized runtime settings for:
  - app URLs
  - API URLs
  - data directory
  - log directory
  - SQLite path
  - CORS origins
  - deployment profile
- Runtime startup validation for production-sensitive settings.
- New runtime health endpoint:

```text
GET /api/v1/health/runtime
```

- Docker Compose improvements:
  - persistent app data volume
  - persistent logs volume
  - FastAPI health check
  - Streamlit health check
  - restart policies
  - production override file
- Secret generation helper:

```bash
python scripts/generate_secrets.py
```

- SQLite backup helper:

```bash
python scripts/backup_sqlite.py --db data/job_assistant.sqlite3 --out-dir backups
```

- SQLite restore helper:

```bash
python scripts/restore_sqlite.py backups/<backup-file>.sqlite3
```

- Smoke test helper:

```bash
python scripts/smoke_test.py
```

- Makefile shortcuts:

```bash
make setup
make secrets
make smoke
make docker-up
make docker-down
make backup
make restore BACKUP=backups/<backup-file>.sqlite3
```

See `docs/PHASE2_DEPLOYMENT.md` for the deployment guide.

### Production-Lite Deployment

Create `.env`:

```bash
cp .env.example .env
python scripts/generate_secrets.py
```

Paste the generated values into `.env`, then set:

```env
ENVIRONMENT=prod
DEPLOYMENT_PROFILE=production
APP_BASE_URL=https://your-app.example.com
API_PUBLIC_URL=https://your-api.example.com
CORS_ORIGINS=https://your-app.example.com
SESSION_COOKIE_SECURE=true
```

Run:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up --build -d
```

### Important Security Note

Provider keys are still user-owned and stored encrypted in the database through the Integrations UI. `.env` should only contain app-level deployment secrets such as `APP_ENCRYPTION_KEY`, `JWT_SECRET_KEY`, public URLs, and runtime configuration.

---

## Phase 3 Implementation Status — Provider Abstraction MVP

Phase 3 adds the first provider-agnostic integration layer while keeping the existing MVP workflows backward compatible.

### Added in Phase 3

- New provider abstraction module:

```text
job_assistant/provider_registry.py
```

- New encrypted per-user provider table:

```text
provider_configs
```

- Provider registry capabilities:
  - base provider interface
  - generic configured-provider adapter
  - manual provider registration
  - provider priority ordering
  - active/inactive providers
  - health status tracking
  - fallback execution
  - audit logging for provider changes

- New FastAPI endpoints:

```text
GET    /api/v1/providers
POST   /api/v1/providers
GET    /api/v1/providers/{platform}/{provider_name}
PUT    /api/v1/providers/{platform}/{provider_name}
DELETE /api/v1/providers/{platform}/{provider_name}
GET    /api/v1/providers/health
POST   /api/v1/providers/execute
```

- Updated health endpoint:

```text
GET /api/v1/health/providers
```

This now returns both legacy integrations and new provider-registry records.

- Updated Streamlit Integrations page:
  - added **Provider registry** tab
  - add/update provider records
  - set platform, provider name, auth type, priority, active status, and config JSON
  - delete provider records
  - view provider health metadata without exposing secrets

- Updated smoke test:

```bash
python scripts/smoke_test.py
```

The smoke test now verifies feedback, database health, provider save, provider health check, and fallback routing.

### Milestone Verification

See:

```text
docs/MILESTONE_VERIFICATION.md
```

Current milestone status:

| Milestone | Status |
|---|---|
| Milestone 1 — MVP Hardening | Achieved |
| Milestone 2 — Docker and Deployment Readiness | Achieved |
| Milestone 3 — Provider Abstraction MVP | Achieved |

### Important Compatibility Note

The older `integration_settings` table remains active so current AI, LinkedIn, RapidAPI, Apify, and Gmail workflows continue working. The new `provider_configs` table is the forward-compatible provider abstraction foundation. Future adapters should gradually migrate real provider execution into `ProviderRegistry`.

## Technical Plan Status - Phase 4, 5, and 6

Implemented in this package:

- Phase 4 AI orchestration MVP with route resolution, AI generation logs, prompt versions, and `/api/v1/ai/*` endpoints.
- Phase 5 automation engine MVP with rules, runs, errors, approval-first execution, and `/api/v1/automation/*` endpoints.
- Phase 6 PostgreSQL migration readiness with Alembic config, first migration, SQLite-to-PostgreSQL migration helper, and migration documentation.

See:

- `docs/PHASE4_AI_ORCHESTRATION.md`
- `docs/PHASE5_AUTOMATION_ENGINE.md`
- `docs/PHASE6_POSTGRES_MIGRATION.md`
- `docs/MILESTONE_4_5_6_VERIFICATION.md`

## Phase 7 status — Team and enterprise foundation

Implemented Milestone 7 foundations:

- organizations
- workspaces
- workspace members
- seeded roles and permissions
- permission checks
- shared resources
- workspace/organization-scoped audit fields
- Team page in Streamlit
- enterprise summary API

See:

- `docs/PHASE7_TEAM_ENTERPRISE_FOUNDATION.md`
- `docs/MILESTONE_7_VERIFICATION.md`

## Workspace-Aware Resource Layer

The team/enterprise foundation now extends into the core resource layer. Opportunities, feedback, integrations, provider configs, AI logs, automation rules/runs/errors, and publishing drafts all carry `workspace_id` and `organization_id` ownership.

Requests may pass `workspace_id` explicitly. If omitted, the user's personal workspace is used. Existing SQLite data is backfilled into each user's personal workspace during startup migration.

A minimal publishing storage layer is included through `posts` and `post_targets`. External publishing execution remains a later publishing-engine milestone.
