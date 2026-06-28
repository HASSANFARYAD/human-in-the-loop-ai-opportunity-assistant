# Configuration

## Environment Variables

All configuration is via environment variables loaded through `config.py` (Pydantic Settings).

### General

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `dev` | Runtime environment: `dev`, `staging`, `prod` |
| `DEPLOYMENT_PROFILE` | `local` | Deployment profile: `local`, `mvp`, `self_hosted`, `staging`, `production` |
| `APP_NAME` | `Job Application Assistant` | Application name |
| `APP_VERSION` | `1.1.0` | Application version |
| `APP_BASE_URL` | `http://localhost:3000` | Frontend base URL |
| `FRONTEND_BASE_URL` | Same as APP_BASE_URL | Frontend base URL for redirects |
| `API_PUBLIC_URL` | `http://localhost:8000` | Public API URL for CORS |
| `API_HOST` | `0.0.0.0` | Server bind host |
| `API_PORT` | `8000` | Server bind port |

### Data & Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_DATA_DIR` | `data` | Data directory for uploads |
| `LOG_DIR` | `logs` | Log directory |
| `MAX_UPLOAD_SIZE_MB` | `10` | Max resume upload size (MB) |
| `MAX_JOBS_PER_USER_FREE` | `50` | Max jobs for free tier |
| `MAX_JOBS_PER_USER_PREMIUM` | `500` | Max jobs for premium tier |

### MongoDB

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URL` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DB_NAME` | `career_assistant` | MongoDB database name |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | `""` | JWT signing secret (min 32 chars in prod) |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` (prod) / `60` (dev) | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token TTL |
| `SESSION_COOKIE_NAME` | `job_assistant_refresh` | Refresh cookie name |
| `SESSION_COOKIE_SECURE` | True in prod | HTTPS-only cookie |
| `SESSION_COOKIE_SAMESITE` | `none` (prod) / `lax` (dev) | Cookie same-site policy |
| `SESSION_COOKIE_PATH` | `/api/v1/auth` | Cookie path scope |
| `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | `60` | Reset token TTL |

### SMTP (Password Reset)

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_HOST` | `""` | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` | `""` | SMTP username |
| `SMTP_PASSWORD` | `""` | SMTP password |
| `SMTP_FROM_EMAIL` | `""` | From email address |
| `SMTP_USE_TLS` | `true` | Enable STARTTLS |

### Encryption

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENCRYPTION_KEY` | `""` | Fernet key for encrypting stored API keys (required in prod) |

### AI & LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_MODEL` | `gpt-4o-mini` | Default model name |
| `DEFAULT_AI_PROVIDER` | `huggingface_local` | Fallback when no provider configured |
| `AI_DAILY_GENERATION_LIMIT` | `50` | Max AI calls per user per day |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMITS_ENABLED` | `true` | Enable rate limiting middleware |
| `RATE_LIMIT_BACKEND` | `mongodb` | Backend: `mongodb`, `redis`, or `gateway` |
| `REDIS_URL` | `""` | Redis connection URL (for Redis backend) |
| `RATE_LIMIT_PER_MINUTE` | `120` | General API rate limit |
| `RATE_LIMIT_AI_PER_HOUR` | `60` | AI generation calls per hour |
| `RATE_LIMIT_FEEDBACK_PER_HOUR` | `20` | Feedback submissions per hour |
| `RATE_LIMIT_PUBLISH_PER_HOUR` | `20` | Publishing actions per hour |
| `RATE_LIMIT_SSE_PER_MINUTE` | `10` | SSE stream connections per minute |

### Scheduler

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHEDULER_ENABLED` | `true` | Enable background scheduler |

### Backups

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_ENABLED` | `false` | Enable automated MongoDB backups |
| `BACKUP_DIR` | `{APP_DATA_DIR}/backups` | Backup output directory |
| `BACKUP_INTERVAL_HOURS` | `24` | Backup frequency |
| `BACKUP_RETENTION` | `30` | Number of backups to retain |
| `BACKUP_S3_BUCKET` | `""` | S3 bucket for offsite backups |
| `BACKUP_S3_ENDPOINT` | `""` | S3-compatible endpoint URL |
| `BACKUP_S3_ACCESS_KEY` | `""` | S3 access key |
| `BACKUP_S3_SECRET_KEY` | `""` | S3 secret key |
| `BACKUP_S3_PREFIX` | `db` | S3 key prefix |

### Follow-up Reminders

| Variable | Default | Description |
|----------|---------|-------------|
| `FOLLOWUP_REMINDERS_ENABLED` | `false` | Enable auto follow-up reminders |
| `FOLLOWUP_AFTER_DAYS` | `7` | Days after which to remind |
| `FOLLOWUP_INTERVAL_HOURS` | `24` | Check interval |

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSERVABILITY_ENABLED` | `true` | Enable metrics collection |
| `TRACING_ENABLED` | `true` | Enable latency tracing |
| `METRICS_RETENTION_DAYS` | `14` | Metrics data retention |
| `ERROR_ALERT_THRESHOLD_PER_HOUR` | `10` | Error rate alert threshold |
| `LATENCY_ALERT_THRESHOLD_MS` | `3000` | Latency alert threshold |
| `SENTRY_DSN` | `""` | Sentry DSN (blank = disabled) |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` | Sentry trace sample rate |

### Worker Queue

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKER_BACKEND` | `mongodb` | Queue backend |
| `WORKER_POLL_INTERVAL_SECONDS` | `5` | Poll interval |
| `WORKER_MAX_ATTEMPTS` | `3` | Max retry attempts |

### Publishing

| Variable | Default | Description |
|----------|---------|-------------|
| `PUBLISHING_REQUIRE_APPROVAL` | `true` | Require approval before publish |
| `PUBLISHING_DRY_RUN` | `true` | Dry-run mode (no actual publishing) |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` (prod) / `DEBUG` (dev) | Log level |
| `LOG_FILE` | `{LOG_DIR}/job_assistant.log` (prod) | Log file path |
| `LOG_MAX_BYTES` | `10485760` | Max log file size |
| `LOG_BACKUP_COUNT` | `5` | Number of rotated log files |

### Compliance

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIT_RETENTION_DAYS` | `365` | Audit log retention |
| `EXPORT_RETENTION_DAYS` | `7` | GDPR export retention |

### CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:3001` | Allowed origins |
| `CORS_ALLOW_CREDENTIALS` | `true` | Allow cookies in CORS |

### Google/Gmail

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CREDENTIALS_FILE` | `credentials.json` | Gmail OAuth credentials file |
| `GOOGLE_TOKEN_FILE` | `token.json` | Gmail OAuth token file |

---

## Frontend Configuration

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Backend API base URL |

---

## AI Provider Configuration (Per-User, in-app)

Users configure AI providers through the Integrations UI. Supported providers:

| Provider | Config Key | Parameters |
|----------|------------|------------|
| OpenAI | `openai` | model, api_key, base_url, max_tokens, temperature |
| Azure OpenAI | `azure_openai` | model, api_key, endpoint, deployment, api_version |
| Anthropic Claude | `claude` | model, api_key |
| Google Gemini | `gemini` | model, api_key |
| Grok (xAI) | `grok` | model, api_key |
| Groq | `groq` | model, api_key |
| Hugging Face API | `huggingface` | model, api_key |
| Hugging Face Local | `huggingface_local` | model (no key required) |
| Ollama | `ollama` | model, base_url (no key required) |
