# Phase 2 Deployment Readiness

This phase keeps the MVP SQLite-first architecture but makes the app safer and easier to deploy locally, on a VM, or in a self-hosted environment.

## What Phase 2 Adds

- Deployment profiles: `local`, `mvp`, `self_hosted`, `staging`, `production`
- Centralized runtime directories for data and logs
- Runtime health endpoint: `/api/v1/health/runtime`
- Docker Compose with persistent `app_data` and `app_logs` volumes
- Streamlit and FastAPI health checks
- Production Compose override
- Secret generation script
- SQLite backup and restore scripts
- Smoke-test script
- Makefile shortcuts

## Local Setup

```bash
cp .env.example .env
make setup
make secrets
```

Paste the generated `APP_ENCRYPTION_KEY` and `JWT_SECRET_KEY` values into `.env`.

Run the app:

```bash
make docker-up
```

Open:

- Streamlit: http://localhost:8501
- FastAPI health: http://localhost:8000/api/v1/health
- Runtime health: http://localhost:8000/api/v1/health/runtime

## Production-Lite Run

Set production values in `.env`:

```bash
ENVIRONMENT=prod
DEPLOYMENT_PROFILE=production
APP_BASE_URL=https://your-app.example.com
API_PUBLIC_URL=https://your-api.example.com
CORS_ORIGINS=https://your-app.example.com
SESSION_COOKIE_SECURE=true
APP_ENCRYPTION_KEY=<generated-fernet-key>
JWT_SECRET_KEY=<generated-secret>
```

Run with the production override:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up --build -d
```

## SQLite Backup

```bash
make backup
```

Or manually:

```bash
python scripts/backup_sqlite.py --db data/job_assistant.sqlite3 --out-dir backups
```

## SQLite Restore

```bash
make restore BACKUP=backups/job_assistant_YYYYMMDDTHHMMSSZ.sqlite3
```

The restore script creates a safety copy of the current database before replacing it.

## Smoke Test

```bash
make smoke
```

The smoke test creates an isolated temporary database, runs migrations, checks DB health, writes feedback, and verifies runtime metadata.

## Notes

Provider API keys are still stored per user in the encrypted database integration store. `.env` is reserved for app-level secrets and deployment settings only.
