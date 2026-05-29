# Phase 3 — Provider Abstraction MVP

Phase 3 adds the first provider-agnostic foundation while preserving the existing Streamlit/FastAPI/SQLite MVP.

## What was added

- `provider_configs` SQLite table for per-user provider records.
- Encrypted provider credentials using the existing application encryption helper.
- Provider registry module:
  - `BaseProvider`
  - `ConfiguredProvider`
  - `ProviderRegistry`
  - provider health checks
  - priority ordering
  - fallback execution
- FastAPI provider endpoints:
  - `GET /api/v1/providers`
  - `POST /api/v1/providers`
  - `GET /api/v1/providers/{platform}/{provider_name}`
  - `PUT /api/v1/providers/{platform}/{provider_name}`
  - `DELETE /api/v1/providers/{platform}/{provider_name}`
  - `GET /api/v1/providers/health`
  - `POST /api/v1/providers/execute`
- Streamlit Integrations tab for adding, updating, viewing, and deleting provider-registry records.
- Provider health metadata:
  - `health_status`
  - `last_health_check_at`
  - `last_success_at`
  - `last_failure_at`
  - `success_count`
  - `failure_count`
  - `last_error`
- Audit logs for provider create/update/delete actions.
- Smoke test coverage for provider save, health check, and fallback routing.

## Data model

The new `provider_configs` table stores one provider per user/platform/provider tuple.

Important columns:

- `user_id`
- `platform`
- `provider_name`
- `auth_type`
- `encrypted_credentials`
- `config_json`
- `priority`
- `is_active`
- `health_status`
- `success_count`
- `failure_count`

Credentials are encrypted before they are stored. API responses expose only `has_credentials`, not raw secrets.

## Fallback model

Provider fallback uses priority ordering:

1. Load active providers for the requested platform.
2. Sort by lowest priority number.
3. Validate credentials.
4. Execute through the first usable provider.
5. If a provider is missing credentials or fails, record health metadata and try the next provider.
6. Return a failure only if no provider can handle the action.

## Backward compatibility

The previous `integration_settings` table remains in place. Existing app features such as AI keys, LinkedIn, RapidAPI, and Apify continue working while new provider-specific adapters are introduced incrementally.

The provider registry is now ready for platform adapters such as:

- OpenAI / Anthropic / Gemini AI adapters
- LinkedIn official API adapter
- RapidAPI LinkedIn adapter
- Apify adapter
- Custom REST API adapter
- Webhook adapter

## Local verification

Run:

```bash
python scripts/smoke_test.py
```

Expected result includes:

```json
"provider_registry": {
  "configured": 1,
  "health_status": "healthy",
  "fallback_provider": "openai"
}
```
