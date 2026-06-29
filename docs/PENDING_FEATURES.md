# Pending Features

## High Priority

1. ~~**Company research-backed interview prep** — currently generates generic behavioral/technical questions; lacks live company context (financials, recent news, product launches, culture). Would require web scraping or an external API per job.~~ ✅ Fixed — `services/company_research.py` provides AI-powered company briefs with MongoDB caching (7-day TTL), integrated into both LLM and fallback interview prep paths.
2. **Freshness filter on discovery** — public job feeds return all listings regardless of posting date. No configurable cutoff (e.g. "last 7 days") before import.

## Medium Priority

3. **Publishing engine live execution** — draft, approval, and target validation work but `publish` is dry-run by default (`PUBLISHING_DRY_RUN=true`). No live social platform publishing.
4. **Fuzzy dedup for near-duplicate job titles** — exact title+company matching misses "Sr. Software Engineer" vs "Senior Software Engineer". No Levenshtein/similarity scoring in the dedup pipeline.
5. **Rate limiter Redis backend** — MongoDB-based rate limiting works for single-instance deploys but lacks atomicity guarantees under high concurrency. Redis backend is optional and untested.

## Low Priority

6. **LinkedIn official SDK integration** — `linkedin_integration.py` is a placeholder. LinkedIn discovery goes through RapidAPI / Apify instead.
7. **Schema migrations CLI** — migration functions exist in `db.py` but there's no CLI command to run/rollback migrations independently of app startup.
8. **Notification system** — no real-time push (email/SMS/in-app) for score drops, follow-up reminders, or interview deadlines beyond app-internal reminders.

## Reference

See the complete feature matrix in `FEATURE_MATRIX.md` and full limitations in `KNOWN_LIMITATIONS.md`.
