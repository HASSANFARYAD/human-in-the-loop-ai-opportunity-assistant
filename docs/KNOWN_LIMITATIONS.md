# Known Limitations

## Partial Implementations

- **Apify Integration**: Supports running actors and normalizing results but has limited error handling and no retry logic.
- **Redis Rate Limiting Backend**: Redis backend is implemented (`rate_limits.py:56-70`) but MongoDB is the default. Redis support depends on `redis-py` and a running Redis instance.

## Technical Debt

- **No API versioning beyond v1**: All endpoints are under `/api/v1/`. No deprecation or migration strategy for breaking changes.
- **Inconsistent test coverage**: Tests exist for specific areas (prompt injection, CSV sanitization, discovery adapters). Frontend tests are absent.

## Performance Limitations

- **Single MongoDB instance**: No connection pooling optimization, no read replicas, no sharding. Suitable for small to medium deployments.
- **No caching layer**: Opportunities and profiles are fetched from MongoDB on every request. No Redis/memcached for frequently accessed data.
- **Synchronous HTTP for AI calls**: AI provider calls block the request thread. For high concurrency, this could exhaust the server's thread pool.
- **Scraper latency**: URL-based scrapers wait for external HTTP responses (15s default timeout). Batch operations may take significant time.

## Security Limitations

- **No brute-force protection on login**: Rate limiting applies per-IP but no exponential backoff or account lockout on failed login attempts.
- **No audit of admin actions**: Admin configuration changes are not separately audited.
- **No role elevation validation**: No MFA or additional verification for role changes.

## Third-Party Limitations

- **Public job board APIs**: May change or deprecate without notice. Rate limits are unenforced but may result in IP blocks.
- **LinkedIn (RapidAPI)**: Requires a RapidAPI subscription. The API may change or require different authentication.
- **Gmail OAuth**: Requires user to complete OAuth flow. Token refresh is not automated for expired credentials.
- **AI Provider Dependencies**: Each provider has its own rate limits, pricing, and availability. The fallback scoring is simpler than AI-assisted scoring.
- **Apify**: Requires an Apify account and API credits. Actor availability varies.
