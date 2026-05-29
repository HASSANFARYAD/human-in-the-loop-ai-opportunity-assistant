# Phase 4 - AI Orchestration MVP

Implemented:

- `job_assistant/ai_orchestrator.py`
- Per-user AI route resolution from `provider_configs` platform `ai`
- Backward compatibility with `integration_settings` service `ai_provider`
- AI generation logging in `ai_generations`
- Prompt version metadata in `prompt_versions`
- API routes under `/api/v1/ai/*`
- Streamlit AI usage and prompt version UI

Human safety posture:

- User-owned keys remain encrypted in the database.
- If no key exists, the app returns deterministic fallback outputs.
- Prompt hashes and metadata are logged; raw prompts are not stored by default.
