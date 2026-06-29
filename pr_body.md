## Summary

Four production-readiness features stacked on `feature/fuzzy-dedup`:

### 1. Fuzzy Dedup
- Expanded `COMMON_ABBREVIATIONS` (40+ entries) in `db/jobs.py`
- Stores `normalized_title` / `normalized_company` in job documents on insert
- Optimized `job_exists()` — tokenized regex query on `normalized_title` (limit 100) instead of loading all user jobs
- Added compound index `(user_id, workspace_id, normalized_title)`

### 2. Security Headers + CSRF
- `job_assistant/security.py`: `SecurityHeadersMiddleware` (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, HSTS, CSP) and `setup_csrf_protection()` (Origin/Referer validation on mutating requests)
- 6 new config vars: `security_headers_enabled`, `hsts_max_age`, `content_security_policy`, `csrf_enabled`, `csrf_exempt_paths`
- Registered in `api_server.py`

### 3. Publishing Engine Live
- `LinkedInProvider` adapter registered with provider registry, delegates to `linkedin_integration.publish_text_post()`
- `publishing_dry_run` default flipped from `true` to `false`

### 4. Integration/E2E Tests
- `tests/test_integration.py` — 24 tests across 5 classes
- Covers freshness filter, security headers, CSRF protection, publishing engine (validation, dry run, live, LinkedIn adapter, lifecycle), and abbreviation expansion
- Full suite: 132 tests, 130 passed, 2 skipped

### Chores
- Updated stale `PUBLISHING_DRY_RUN=true` references in `.env.example`, `docker-compose.yml`, `docs/CONFIGURATION.md`
- Updated `KNOWN_LIMITATIONS.md`, `PENDING_FEATURES.md`, `PRODUCT_AND_ARCHITECTURE.md`
