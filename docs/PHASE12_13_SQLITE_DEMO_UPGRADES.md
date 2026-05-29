# Phase 12 and 13 SQLite Demo Upgrades

Date: 2026-05-25

## Status

Implemented local, no-paid-service foundations for rate limiting, storage health, AI health, and traceable API errors while keeping SQLite as the default demo database.

## Added

- SQLite-backed `usage_counters` table.
- Local API rate-limit middleware.
- Configurable limits in `.env.example`:
  - `RATE_LIMITS_ENABLED`
  - `RATE_LIMIT_PER_MINUTE`
  - `RATE_LIMIT_AI_PER_HOUR`
  - `RATE_LIMIT_FEEDBACK_PER_HOUR`
  - `RATE_LIMIT_PUBLISH_PER_HOUR`
- New API endpoints:
  - `GET /api/v1/health/storage`
  - `GET /api/v1/health/ai`
  - `GET /api/v1/usage`
- Error IDs in unhandled FastAPI error responses.
- SQLite `busy_timeout` and WAL mode for better local demo concurrency.
- Alembic migration `20260525_0004_usage_counters.py`.

## Demo Constraints Preserved

- SQLite remains the default runtime database.
- No Redis, Sentry, Prometheus, paid monitoring, paid queue, or paid storage was added.
- Rate limiting uses the existing local database and can be disabled with `RATE_LIMITS_ENABLED=false`.

## Remaining Production Work

- Replace SQLite rate counters with Redis or gateway-backed limits only when scaling requires it.
- Add external observability such as Sentry/OpenTelemetry only when a production budget and deployment target are chosen.
- Finish the SQLAlchemy repository migration before making PostgreSQL the active production database.
