# Phase 8 — Workspace-Aware Core Resources

This phase makes the main user-owned resources workspace-aware so the team/enterprise foundation can safely support multiple workspaces inside an organization.

## Implemented scope

Workspace and organization ownership is now attached to:

- Opportunities (`jobs`)
- Feedback (`feedback`)
- Legacy integrations (`integration_settings`)
- Provider abstraction configs (`provider_configs`)
- AI logs (`ai_generations`)
- Automation rules (`automation_rules`)
- Automation runs and errors (`automation_runs`, `automation_errors`)
- Publishing drafts (`posts`, `post_targets`)
- Audit logs already supported workspace and organization scope and now receive scope data from core write paths.

## Behavior

- If a request omits `workspace_id`, the user's personal workspace is used.
- If a request includes `workspace_id`, the user must be an active member of that workspace.
- Existing user-owned data is backfilled into each user's personal workspace during SQLite startup migration.
- Integration keys and provider credentials are scoped by `user_id + workspace_id`, so the same user can maintain different keys per workspace.
- Opportunity URL uniqueness is now scoped by `user_id + workspace_id + url`.

## New/updated API support

Most resource endpoints now accept `workspace_id` in the request body or query string:

- `/api/v1/jobs`
- `/api/v1/feedback`
- `/api/v1/integrations/*`
- `/api/v1/providers/*`
- `/api/v1/ai/generations`
- `/api/v1/ai/ask-json`
- `/api/v1/automation/*`
- `/api/v1/posts`
- `/api/v1/audit-logs`

## Publishing foundation

A minimal publishing schema was added:

- `posts`
- `post_targets`

This does not yet implement actual external publishing. It provides the workspace-aware storage layer required before the publishing engine is built out.

## Validation

Validation performed:

- Python compile check
- Database migration smoke test
- Workspace-scoped database CRUD test
- FastAPI route test for jobs, feedback, integrations, providers, automation, and posts
- Existing `scripts/smoke_test.py` still passes

## Remaining recommended work

- Update the Streamlit UI to expose workspace selectors consistently across every page.
- Add permission enforcement per resource action, not only membership validation.
- Convert compact SQLite helpers to SQLAlchemy repositories before full PostgreSQL runtime migration.
- Add publishing approval workflow and provider-backed publishing execution.
