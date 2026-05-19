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

## App Workflow

1. Open `Profile` and save your CV, skills, roles, locations, and preferences.
2. Open `Ingest Opportunities`.
3. Use one of the ingest methods:
   - `Manual / pasted`: paste a job, hackathon, webinar, competition, or URL text.
   - `Public discovery`: search public job APIs by keyword.
   - `CSV upload`: import structured opportunity lists.
   - `Gmail read-only`: import matching alert emails after OAuth setup.
4. Open `Review Queue`.
5. Click `Score all unscored opportunities`.
6. Open `Opportunity Detail` to inspect scoring, update status, add notes, and generate job materials.
7. Use `Reminders` for follow-ups, deadlines, interview dates, event dates, and registration deadlines.

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

- `profile`
- `jobs`
- `evaluations`
- `application_materials`
- `applications`
- `reminders`

The `jobs` table stores all opportunity types, not only jobs.

## Production Readiness

This is still an MVP, not production-ready multi-user software.

Known production gaps:

- no real authentication/authorization on the API
- permissive CORS in development config
- SQLite/local file storage
- local OAuth token handling
- scheduler logs reminders but does not send push/email notifications
- limited automated test coverage

Before production use, add auth, hardened configuration, managed database/storage, proper notification delivery, tests, monitoring, and deployment-specific secrets management.

## Notes On Source Compliance

Public web pages can be visible without login but still disallow automated scraping. This app favors public APIs, feeds, Gmail alerts, CSV import, and manual paste to keep the workflow stable and respectful of source rules.

## Verify

Basic syntax check:

```bash
python -m compileall app.py job_assistant
```
