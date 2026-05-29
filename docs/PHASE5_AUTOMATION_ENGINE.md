# Phase 5 - Automation Engine MVP

Implemented:

- `job_assistant/automation_engine.py`
- `automation_rules`, `automation_runs`, `automation_steps`, and `automation_errors` tables
- API routes under `/api/v1/automation/*`
- Streamlit automation rule, run, and error UI
- Human approval required by default
- Activity notifications for matched rules

Current execution mode:

- Synchronous MVP execution.
- Tables are compatible with a future Redis/Celery/Dramatiq worker.
- Unsafe actions are gated by approval defaults.
