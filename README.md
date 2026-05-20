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

Create a local `.env` file if needed:

```bash
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-5.5
APP_DB_PATH=data/job_assistant.sqlite3
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_TOKEN_FILE=token.json
SCHEDULER_ENABLED=true
JWT_SECRET_KEY=replace-this-with-a-long-random-secret
LOCAL_USER_PASSWORD=replace-default-local-password
```

`OPENAI_API_KEY` is optional. Without it, the app still runs with local rule-based scoring and fallback draft generation.

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

User API keys and integration configs are encrypted before being written to `integration_settings` using Fernet authenticated encryption.

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

The selected provider is used for application-material generation. If no provider key is configured, the app returns safe fallback drafts instead of failing.

### Automation preferences and progress updates

The new Automation page lets each user enable scheduled workflows, configure intervals, decide whether to score new opportunities, and optionally generate materials for high-match jobs. Scheduler runs now write progress updates to `activity_events`, which are shown in the app.

Automation still respects the original safety boundary: the app imports/organizes/scorers/generates drafts, but it does not automatically submit job applications or scrape private pages.
