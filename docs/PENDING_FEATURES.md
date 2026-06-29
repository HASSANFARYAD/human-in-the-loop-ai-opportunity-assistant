# Pending Features

## Medium Priority

1. **Rate limiter Redis backend** — MongoDB-based rate limiting works for single-instance deploys but lacks atomicity guarantees under high concurrency. Redis backend is optional and untested.

## Low Priority

2. **Schema migrations CLI** — migration functions exist in `db.py` but there's no CLI command to run/rollback migrations independently of app startup.
3. **Notification system** — no real-time push (email/SMS/in-app) for score drops, follow-up reminders, or interview deadlines beyond app-internal reminders.

## Reference

See the complete feature matrix in `FEATURE_MATRIX.md` and full limitations in `KNOWN_LIMITATIONS.md`.
