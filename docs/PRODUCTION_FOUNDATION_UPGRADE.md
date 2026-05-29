# Production Foundation Upgrade

Date: 2026-05-25

## Implemented

- SQLAlchemy engine/session/model foundation in `job_assistant/db_sa.py`.
- Optional Redis-backed rate limiting with SQLite fallback.
- Local observability:
  - request metrics
  - latency metrics
  - alert events
  - trace IDs
  - Prometheus-style `/api/v1/metrics`
- Durable worker queue foundation using SQLite tables.
- Safe publishing engine:
  - platform validation
  - approval required by default
  - dry-run by default
  - provider-registry routing for real publish attempts
- Compliance foundation:
  - user data export
  - deletion request review
  - deletion approval after export
  - retention cleanup
  - admin review endpoint
- Optional free self-hosted Redis/PostgreSQL services in Docker Compose profiles.

## Demo Defaults

SQLite remains the default database. Public publishing is disabled by default through:

```text
PUBLISHING_REQUIRE_APPROVAL=true
PUBLISHING_DRY_RUN=true
RATE_LIMIT_BACKEND=sqlite
WORKER_BACKEND=sqlite
```

## Production Toggles

To use Redis for rate limits:

```text
RATE_LIMIT_BACKEND=redis
REDIS_URL=redis://redis:6379/0
```

To start free self-hosted Redis:

```bash
docker compose --profile redis up --build
```

To start free self-hosted PostgreSQL:

```bash
docker compose --profile postgres up --build
```

## Remaining Deployment Work

- Migrate existing legacy SQLite helper write paths to SQLAlchemy repositories before relying on PostgreSQL for all runtime workflows.
- Run Alembic migrations against PostgreSQL in staging.
- Deploy a real worker process/command loop for `worker_jobs`.
- Configure production secrets, HTTPS, restricted CORS, backups, and admin-only access checks.
