# Deployment

## Prerequisites

A **MongoDB** instance is required. All business data, agent memory, AI generation logs, rate-limit counters, and conversation data are stored in MongoDB. Options:

- **MongoDB Atlas** (free M0 tier is sufficient for small deployments)
- **Render MongoDB** (add via Render dashboard)
- **Self-hosted** on the same instance or a nearby VM

## Backend On Render

Use `deploy/render.yaml` as the Render blueprint. It deploys the `backend` Dockerfile and starts Uvicorn with Render's `$PORT`.

Required environment variables:

```bash
ENVIRONMENT=prod
DEPLOYMENT_PROFILE=mvp
APP_DATA_DIR=/var/data/job-assistant
LOG_DIR=/var/data/job-assistant/logs
FRONTEND_BASE_URL=https://your-app.vercel.app
APP_BASE_URL=https://your-app.vercel.app
API_PUBLIC_URL=https://your-render-service.onrender.com
CORS_ORIGINS=https://your-app.vercel.app
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=none
JWT_SECRET_KEY=<long-random-secret>
APP_ENCRYPTION_KEY=<fernet-key>

# MongoDB (required)
MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=career_assistant
```

Health checks:

- `/api/v1/health`
- `/api/v1/health/db`
- `/api/v1/health/storage`

## Frontend On Vercel

Deploy from `frontend`.

Required environment variable:

```bash
NEXT_PUBLIC_API_URL=https://your-render-service.onrender.com
```

The backend must include the exact Vercel app origin in `CORS_ORIGINS`. Because auth refresh uses cookies, keep `CORS_ALLOW_CREDENTIALS=true`; for cross-site Vercel-to-Render cookies use `SESSION_COOKIE_SECURE=true` and `SESSION_COOKIE_SAMESITE=none`.

## Database Cleanup

Dry-run:

```bash
cd backend
python scripts/clear_jobs.py
```

Confirmed cleanup:

```bash
cd backend
python scripts/clear_jobs.py --confirm
```
