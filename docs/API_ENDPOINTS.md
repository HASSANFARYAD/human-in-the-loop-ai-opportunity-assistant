# API Endpoints

All endpoints are under `/api/v1/` prefix. Authentication via Bearer JWT token.

## Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | General health + startup warnings |
| GET | `/health/runtime` | No | Runtime info (env, deployment profile, DB engine) |
| GET | `/health/db` | No | MongoDB connection health |
| GET | `/health/storage` | No | Data directory write check |
| GET | `/health/providers` | Yes | Configured integrations and providers |
| GET | `/health/ai` | Yes | AI provider route info + optional probe |

## Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | No | Register with email + password + full_name |
| POST | `/auth/login` | No | Login, returns access_token + sets refresh cookie |
| POST | `/auth/forgot-password` | No | Request password reset email |
| POST | `/auth/reset-password` | No | Reset password with token |
| POST | `/auth/refresh` | Cookie | Refresh access token using cookie |
| POST | `/auth/logout` | Cookie | Logout, revoke refresh token |
| GET | `/auth/me` | Yes | Current user info |

## Profile

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/profile` | Yes | Get default profile |
| POST | `/profile` | Yes | Upsert default profile |
| POST | `/profile/upload-resume` | Yes | Upload resume (PDF/DOCX/TXT), AI extracts fields |
| GET | `/profiles` | Yes | List all profiles |
| POST | `/profiles` | Yes | Create new profile |
| PUT | `/profiles/{id}` | Yes | Update profile by ID |
| POST | `/profiles/{id}/default` | Yes | Set profile as default |
| DELETE | `/profiles/{id}` | Yes | Delete profile |

## Jobs / Opportunities

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/jobs` | Yes | List jobs (query: workspace_id, content_type) |
| POST | `/jobs` | Yes | Create job manually |
| GET | `/jobs/{id}` | Yes | Get job detail with evaluation |
| DELETE | `/jobs/{id}` | Yes | Delete job and related data |
| POST | `/jobs/{id}/score` | Yes | Score job against profile (query: profile_id) |
| POST | `/jobs/score-batch` | Yes | Batch score jobs |
| POST | `/jobs/{id}/score-feedback` | Yes | Submit relevance feedback |

## Discovery

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/discover/extract` | Yes | Extract job from pasted text/URL |
| POST | `/discover/public` | Yes | Discover from public job feeds |
| POST | `/discover/from-profile` | Yes | Auto-discover from user profile |
| POST | `/discover/import` | Yes | Import pre-found opportunities |
| POST | `/discover/import-url` | Yes | Import from URL with scraping |
| POST | `/discover/manual` | Yes | Manual entry (structured form) |
| POST | `/discover/rapidapi-linkedin` | Yes | Search LinkedIn via RapidAPI |
| POST | `/discover/apify` | Yes | Run Apify actor for URL |

## Application Materials

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/jobs/{id}/materials` | Yes | Get saved materials |
| POST | `/jobs/{id}/generate-materials` | Yes | Generate materials (cover letter, etc.) |
| POST | `/jobs/{id}/tailor-resume` | Yes | Generate tailored resume (query: profile_id) |
| POST | `/jobs/{id}/resume-review` | Yes | Resume review against job |
| GET | `/profile/resume-reviews` | Yes | List resume reviews (query: job_id) |
| POST | `/jobs/{id}/interview-prep` | Yes | Generate interview prep |
| GET | `/jobs/{id}/interview-prep` | Yes | List interview prep sessions |

## Resume Builder

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/resume-templates` | Yes | List available country templates |
| POST | `/jobs/{id}/resume-document` | Yes | Generate and download DOCX resume (query: template, profile_id) |

## Recordings

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/recordings` | Yes | List recordings (query: job_id) |
| POST | `/recordings` | Yes | Save recording (data_url) |
| POST | `/recordings/upload` | Yes | Upload recording file (multipart) |

## Reminders

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/reminders` | Yes | Create reminder |

## Agent (Conversational AI)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/agent/chat` | Yes | Non-streaming chat (intent classification + execution) |
| POST | `/agent/chat/stream` | Yes | Streaming chat via SSE |
| POST | `/agent/conversations` | Yes | Create conversation |
| GET | `/agent/conversations` | Yes | List conversations |
| GET | `/agent/conversations/{id}` | Yes | Get conversation with messages |
| PATCH | `/agent/conversations/{id}` | Yes | Update conversation title |
| DELETE | `/agent/conversations/{id}` | Yes | Delete conversation |
| POST | `/agent/conversations/{id}/feedback` | Yes | Thumbs up/down on message |
| GET | `/agent/persona` | Yes | Get agent persona |
| PUT | `/agent/persona` | Yes | Update agent persona |
| GET | `/agent/memories` | Yes | List agent memories |
| POST | `/agent/memories` | Yes | Create memory |
| PUT | `/agent/memories/{id}` | Yes | Update memory |
| DELETE | `/agent/memories/{id}` | Yes | Delete memory |
| GET | `/admin/prompts` | Yes | List prompt versions |
| POST | `/admin/prompts` | Yes | Create/update prompt version |
| DELETE | `/admin/prompts` | Yes | Delete prompt version (query: name, version) |

## AI / Usage

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/ai/ask-json` | Yes | Direct AI call (system + prompt → JSON) |
| GET | `/ai/generations` | Yes | List AI generation logs |
| GET | `/ai/usage` | Yes | Daily budget + usage breakdown |
| GET | `/ai/prompts` | Yes | List prompt versions |
| POST | `/ai/prompts` | Yes | Save prompt version |
| GET | `/rate-limits` | Yes | Current rate limit status |

## Integrations

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/integrations` | Yes | List configured integrations |
| GET | `/integrations/{service}` | Yes | Get integration settings |
| PUT | `/integrations/{service}` | Yes | Create/update integration |
| DELETE | `/integrations/{service}` | Yes | Remove integration |

## Providers

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/providers` | Yes | List provider configs (query: platform) |
| POST | `/providers` | Yes | Create provider config |
| GET | `/providers/{platform}/{name}` | Yes | Get provider config |
| PUT | `/providers/{platform}/{name}` | Yes | Update provider config |
| DELETE | `/providers/{platform}/{name}` | Yes | Delete provider config |
| GET | `/providers/health` | Yes | Provider health checks |
| POST | `/providers/execute` | Yes | Execute provider action with fallback |

## Admin Config

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/admin/configs` | Admin | List all admin configs |
| GET | `/admin/configs/{type}` | Admin | List by type |
| POST | `/admin/configs` | Admin | Create admin config |
| PUT | `/admin/configs/{type}/{id}` | Admin | Update admin config |
| POST | `/admin/configs/{type}/{id}/activate` | Admin | Activate config |
| POST | `/admin/configs/{type}/{id}/deactivate` | Admin | Deactivate config |
| POST | `/admin/configs/{type}/{id}/test` | Admin | Test configuration |

## Automation

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/automation/rules` | Yes | List automation rules |
| POST | `/automation/rules` | Yes | Create rule |
| PUT | `/automation/rules/{id}` | Yes | Update rule |
| DELETE | `/automation/rules/{id}` | Yes | Delete rule |
| GET | `/automation/runs` | Yes | List run history |
| GET | `/automation/errors` | Yes | List automation errors |
| POST | `/automation/trigger` | Yes | Trigger automation event |

## Publishing

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/posts` | Yes | Create post |
| GET | `/posts` | Yes | List posts |
| POST | `/posts/{id}/approve` | Yes | Approve post |
| POST | `/posts/{id}/publish` | Yes | Publish post |
| POST | `/targets/validate` | Yes | Validate publishing target |

## Team / Enterprise

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/enterprise/bootstrap` | Yes | Auto-bootstrap workspace |
| GET | `/enterprise/summary` | Yes | Enterprise summary |
| GET | `/workspaces` | Yes | List user workspaces |
| POST | `/organizations` | Yes | Create organization |
| POST | `/workspaces` | Yes | Create workspace |
| GET | `/workspaces/{id}/members` | Yes | List workspace members |
| POST | `/workspaces/{id}/members` | Yes | Add member |
| GET | `/roles` | Yes | List roles |
| GET | `/permissions` | Yes | List permissions (query: role) |
| GET | `/permissions/check` | Yes | Check permission (query: workspace_id, permission) |
| GET | `/shared-resources` | Yes | List shared resources |
| POST | `/shared-resources` | Yes | Share resource |

## Activity & Feedback

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/activity` | Yes | List activity events |
| GET | `/feedback` | Yes | List feedback |
| POST | `/feedback` | Yes | Submit feedback |
| PUT | `/feedback/{id}/status` | Admin | Update feedback status |
| GET | `/audit-logs` | Admin | List audit logs |

## Usage & Observability

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/usage` | Yes | Usage summary |
| GET | `/observability` | Yes | Metrics summary (query: hours) |
| GET | `/metrics` | Yes | Prometheus text format |
| POST | `/alerts/{id}/ack` | Admin | Acknowledge alert |

## Workers

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/workers/health` | Admin | Worker queue health |
| GET | `/workers/jobs` | Admin | List worker jobs |
| POST | `/workers/jobs` | Admin | Enqueue worker job |

## Compliance

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/compliance/export` | Yes | Request data export |
| GET | `/compliance/exports` | Yes | List exports |
| POST | `/compliance/delete-request` | Yes | Request data deletion |
| POST | `/compliance/delete-approve` | Admin | Approve deletion |
| POST | `/compliance/apply-retention` | Admin | Apply retention policies |

## Gmail

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/gmail/auth-url` | Yes | Get Gmail OAuth URL |
| GET | `/gmail/callback` | No | Gmail OAuth callback |
| POST | `/gmail/messages` | Yes | Import Gmail messages |
| GET | `/gmail/messages` | Yes | List Gmail messages |
| POST | `/gmail/disconnect` | Yes | Disconnect Gmail |

## Scheduler

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/scheduler/start` | Yes | Start scheduler |
| POST | `/scheduler/stop` | Yes | Stop scheduler |
| GET | `/scheduler/status` | Yes | Scheduler status |
