# Known Limitations

## Missing Features

- ~~**Company Research-backed Interview Prep**: No dedicated company research module exists. Interview questions may include general company-specific questions but lack automated web research, company profile caching, or a dedicated company brief UI.~~ ✅ Fixed — added `services/company_research.py` with AI-powered research and MongoDB-backed 7-day cache; integrated into both LLM and fallback interview prep paths.
- ~~**Freshness Filter on Discovery**: Public job sources return results without date-based filtering. No env config or UI for filtering opportunities by recency. Marked as high priority in PENDING_FEATURES.md.~~ ✅ Fixed — added `_freshness_filter()` to `public_discovery.py`, `max_age_days` query param and dropdown UI in Find Jobs, `DISCOVERY_FRESHNESS_DAYS` env config (default 30 days).
- ~~**Publishing Engine (Live)**: The publishing engine operates in dry-run mode by default (`PUBLISHING_DRY_RUN=true`). Actual posting to external platforms (LinkedIn, Twitter) is not implemented.~~ ✅ Fixed — `PUBLISHING_DRY_RUN` now defaults to `false`. A `LinkedInProvider` adapter class registered with the provider registry calls the real LinkedIn API (`linkedin_integration.publish_text_post`) using user-configured credentials and author URN.

## Partial Implementations

- ~~**Indeed/Seek/LinkedIn Scrapers**: URL-based scrapers depend on external website structure. They may break if the target site changes its HTML. Limited error handling. Indeed often returns 403 (blocked).~~ ✅ Fixed — added `SeekScraper` (seek.com.au), `LinkedInScraper` (backed by RapidAPI), retry logic with exponential backoff, user-agent rotation, and anti-block detection.
- **Apify Integration**: Supports running actors and normalizing results but has limited error handling and no retry logic.
- **Redis Rate Limiting Backend**: Redis backend is implemented (`rate_limits.py:56-70`) but MongoDB is the default. Redis support depends on `redis-py` and a running Redis instance.
- ~~**Company-specific Interview Questions**: Generated via AI without a dedicated company research pipeline. Quality depends on the AI provider's training data.~~ ✅ Fixed — now uses `services/company_research.py` to enrich both fallback and LLM interview prep with live company context (description, industry, news, culture, products).

## Technical Debt

- ~~**`api.py`** was split into 16 domain route modules (`routes/` package). `api.py` is now a 14-line aggregator.~~ ✅ Fixed in PR #24 (53cfbe8)
- ~~**`db.py`** was split into 13 domain sub-modules (`db/` package). Each module is under 650 lines.~~ ✅ Fixed in PR #24 (53cfbe8)
- **No API versioning beyond v1**: All endpoints are under `/api/v1/`. No deprecation or migration strategy for breaking changes.
- **Inconsistent test coverage**: Tests exist for specific areas (prompt injection, CSV sanitization, discovery adapters) but no integration tests, E2E tests, or frontend tests.

## Performance Limitations

- **Single MongoDB instance**: No connection pooling optimization, no read replicas, no sharding. Suitable for small to medium deployments.
- **No caching layer**: Opportunities and profiles are fetched from MongoDB on every request. No Redis/memcached for frequently accessed data.
- **Synchronous HTTP for AI calls**: AI provider calls block the request thread. For high concurrency, this could exhaust the server's thread pool.
- **Scraper latency**: URL-based scrapers wait for external HTTP responses (15s default timeout). Batch operations may take significant time.

## Security Limitations

- ~~**No CSRF protection**: API endpoints accept cookies without CSRF tokens. Session cookies are scoped to `/api/v1/auth` to mitigate.~~ ✅ Fixed — added Origin/Referer header validation via `setup_csrf_protection()` in `security.py`, with configurable exempt paths (`CSRF_EXEMPT_PATHS`), toggled by `CSRF_ENABLED`.
- ~~**No security headers in response**: No `Content-Security-Policy`, `X-Frame-Options`, or `Strict-Transport-Security` headers.~~ ✅ Fixed — `SecurityHeadersMiddleware` in `security.py` sets `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security` (HSTS), and `Content-Security-Policy`, toggled by `SECURITY_HEADERS_ENABLED`.
- **No brute-force protection on login**: Rate limiting applies per-IP but no exponential backoff or account lockout on failed login attempts.
- **No audit of admin actions**: Admin configuration changes are not separately audited.
- **No role elevation validation**: No MFA or additional verification for role changes.

## Third-Party Limitations

- **Public job board APIs**: May change or deprecate without notice. Rate limits are unenforced but may result in IP blocks.
- **LinkedIn (RapidAPI)**: Requires a RapidAPI subscription. The API may change or require different authentication.
- **Gmail OAuth**: Requires user to complete OAuth flow. Token refresh is not automated for expired credentials.
- **AI Provider Dependencies**: Each provider has its own rate limits, pricing, and availability. The fallback scoring is simpler than AI-assisted scoring.
- **Apify**: Requires an Apify account and API credits. Actor availability varies.
