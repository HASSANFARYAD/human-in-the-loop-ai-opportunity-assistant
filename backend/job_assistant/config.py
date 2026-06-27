import os
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class DeploymentProfile(str, Enum):
    LOCAL = "local"
    MVP = "mvp"
    SELF_HOSTED = "self_hosted"
    STAGING = "staging"
    PRODUCTION = "production"


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class Settings(BaseSettings):
    environment: Environment = Environment(os.getenv("ENVIRONMENT", "dev"))
    deployment_profile: DeploymentProfile = DeploymentProfile(os.getenv("DEPLOYMENT_PROFILE", "local"))

    app_name: str = os.getenv("APP_NAME", "Job Application Assistant")
    app_version: str = os.getenv("APP_VERSION", "1.1.0")
    app_base_url: str = os.getenv("APP_BASE_URL", "http://localhost:3000")
    frontend_base_url: str = os.getenv("FRONTEND_BASE_URL", os.getenv("APP_BASE_URL", "http://localhost:3000"))
    api_public_url: str = os.getenv("API_PUBLIC_URL", "http://localhost:8000")

    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    app_data_dir: str = os.getenv("APP_DATA_DIR", "data")
    log_dir: str = os.getenv("LOG_DIR", "logs")
    mongo_url: Optional[str] = os.getenv("MONGO_URL")
    mongo_db_name: str = os.getenv("MONGO_DB_NAME", "career_assistant")

    # User-owned provider API keys are stored encrypted in the database from the Integrations UI.
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    default_ai_provider: str = os.getenv("DEFAULT_AI_PROVIDER", "huggingface_local")

    google_credentials_file: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    google_token_file: str = os.getenv("GOOGLE_TOKEN_FILE", "token.json")

    scheduler_enabled: bool = _bool_env("SCHEDULER_ENABLED", True)
    rate_limits_enabled: bool = _bool_env("RATE_LIMITS_ENABLED", True)

    # Automated database backups (runs on its own scheduler, independent of SCHEDULER_ENABLED).
    backup_enabled: bool = _bool_env("BACKUP_ENABLED", False)
    backup_dir: str = os.getenv("BACKUP_DIR", str(Path(os.getenv("APP_DATA_DIR", "data")) / "backups"))
    backup_interval_hours: int = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
    backup_retention: int = int(os.getenv("BACKUP_RETENTION", "30"))
    backup_s3_bucket: str = os.getenv("BACKUP_S3_BUCKET", "")
    backup_s3_endpoint: str = os.getenv("BACKUP_S3_ENDPOINT", "")
    backup_s3_access_key: str = os.getenv("BACKUP_S3_ACCESS_KEY", "")
    backup_s3_secret_key: str = os.getenv("BACKUP_S3_SECRET_KEY", "")
    backup_s3_prefix: str = os.getenv("BACKUP_S3_PREFIX", "db")

    # Automated follow-up reminders for stale applications (own scheduler).
    followup_reminders_enabled: bool = _bool_env("FOLLOWUP_REMINDERS_ENABLED", False)
    followup_after_days: int = int(os.getenv("FOLLOWUP_AFTER_DAYS", "7"))
    followup_interval_hours: int = int(os.getenv("FOLLOWUP_INTERVAL_HOURS", "24"))

    # Error monitoring (Sentry). Leave blank to disable.
    sentry_dsn: str = os.getenv("SENTRY_DSN", "")
    sentry_traces_sample_rate: float = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0"))
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
    rate_limit_ai_per_hour: int = int(os.getenv("RATE_LIMIT_AI_PER_HOUR", "60"))
    rate_limit_feedback_per_hour: int = int(os.getenv("RATE_LIMIT_FEEDBACK_PER_HOUR", "20"))
    rate_limit_publish_per_hour: int = int(os.getenv("RATE_LIMIT_PUBLISH_PER_HOUR", "20"))
    rate_limit_sse_per_minute: int = int(os.getenv("RATE_LIMIT_SSE_PER_MINUTE", "10"))
    rate_limit_backend: str = os.getenv("RATE_LIMIT_BACKEND", "mongodb")
    ai_daily_generation_limit: int = int(os.getenv("AI_DAILY_GENERATION_LIMIT", "50"))
    redis_url: Optional[str] = os.getenv("REDIS_URL")

    observability_enabled: bool = _bool_env("OBSERVABILITY_ENABLED", True)
    tracing_enabled: bool = _bool_env("TRACING_ENABLED", True)
    metrics_retention_days: int = int(os.getenv("METRICS_RETENTION_DAYS", "14"))
    error_alert_threshold_per_hour: int = int(os.getenv("ERROR_ALERT_THRESHOLD_PER_HOUR", "10"))
    latency_alert_threshold_ms: int = int(os.getenv("LATENCY_ALERT_THRESHOLD_MS", "3000"))

    worker_backend: str = os.getenv("WORKER_BACKEND", "mongodb")
    worker_poll_interval_seconds: int = int(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "5"))
    worker_max_attempts: int = int(os.getenv("WORKER_MAX_ATTEMPTS", "3"))

    publishing_require_approval: bool = _bool_env("PUBLISHING_REQUIRE_APPROVAL", True)
    publishing_dry_run: bool = _bool_env("PUBLISHING_DRY_RUN", True)

    audit_retention_days: int = int(os.getenv("AUDIT_RETENTION_DAYS", "365"))
    export_retention_days: int = int(os.getenv("EXPORT_RETENTION_DAYS", "7"))

    log_level: str = os.getenv("LOG_LEVEL", "INFO" if os.getenv("ENVIRONMENT") == "prod" else "DEBUG")
    log_file: Optional[str] = os.getenv("LOG_FILE") or (str(Path(os.getenv("LOG_DIR", "logs")) / "job_assistant.log") if os.getenv("ENVIRONMENT") == "prod" else None)
    log_max_bytes: int = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
    log_backup_count: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))

    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15" if os.getenv("ENVIRONMENT") == "prod" else "60"))
    refresh_token_expire_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "job_assistant_refresh")
    session_cookie_secure: bool = _bool_env("SESSION_COOKIE_SECURE", os.getenv("ENVIRONMENT", "dev") == "prod")
    session_cookie_samesite: str = os.getenv("SESSION_COOKIE_SAMESITE", "none" if os.getenv("ENVIRONMENT", "dev") == "prod" else "lax").strip().lower()
    session_cookie_path: str = os.getenv("SESSION_COOKIE_PATH", "/api/v1/auth")
    password_reset_token_expire_minutes: int = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "60"))
    frontend_reset_password_url: str = os.getenv("FRONTEND_RESET_PASSWORD_URL", f"{os.getenv('FRONTEND_BASE_URL', os.getenv('APP_BASE_URL', 'http://localhost:3000')).rstrip('/')}/reset-password")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "")
    smtp_use_tls: bool = _bool_env("SMTP_USE_TLS", True)
    app_encryption_key: Optional[str] = os.getenv("APP_ENCRYPTION_KEY")

    max_upload_size_mb: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    max_jobs_per_user_free: int = int(os.getenv("MAX_JOBS_PER_USER_FREE", "50"))
    max_jobs_per_user_premium: int = int(os.getenv("MAX_JOBS_PER_USER_PREMIUM", "500"))

    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
    cors_allow_credentials: bool = _bool_env("CORS_ALLOW_CREDENTIALS", True)

    model_config = ConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PROD

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEV

    @property
    def effective_database_url(self) -> str:
        return self.mongo_url or "mongodb://localhost:27017"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def session_cookie_max_age_seconds(self) -> int:
        return self.refresh_token_expire_days * 24 * 60 * 60

    def ensure_runtime_dirs(self) -> None:
        Path(self.app_data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)
        if self.log_file:
            Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)

    def validate_secrets(self) -> None:
        if self.is_production:
            if not self.app_encryption_key:
                raise RuntimeError(
                    "APP_ENCRYPTION_KEY is required in production. "
                    "Run: python scripts/generate_secrets.py"
                )
            if not self.jwt_secret_key or len(self.jwt_secret_key) < 32:
                raise RuntimeError(
                    "JWT_SECRET_KEY is required in production (min 32 characters). "
                    "Run: python scripts/generate_secrets.py"
                )

    def startup_warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.is_production:
            if not self.app_encryption_key:
                warnings.append("APP_ENCRYPTION_KEY is required in production for encrypted user provider keys.")
            if not self.jwt_secret_key or self.jwt_secret_key in {"dev-secret-key-change-in-prod", "change-me-before-production"} or len(self.jwt_secret_key) < 32:
                warnings.append("JWT_SECRET_KEY must be changed before production use (min 32 characters).")
            if len(self.jwt_secret_key) < 32:
                warnings.append("JWT_SECRET_KEY should be at least 32 characters in production.")
            if "*" in self.cors_origin_list:
                warnings.append("CORS_ORIGINS must not include wildcard origins in production.")
            if not self.cors_origin_list or any(origin.startswith("http://") for origin in self.cors_origin_list):
                warnings.append("CORS_ORIGINS should contain explicit HTTPS origins in production.")
            if not self.cors_allow_credentials:
                warnings.append("CORS_ALLOW_CREDENTIALS must be true in production so refresh cookies can be sent by the trusted frontend.")
            if not self.session_cookie_secure:
                warnings.append("SESSION_COOKIE_SECURE should be true behind HTTPS in production.")
            if self.session_cookie_samesite not in {"lax", "strict", "none"}:
                warnings.append("SESSION_COOKIE_SAMESITE must be one of lax, strict, or none.")
            if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
                warnings.append("SESSION_COOKIE_SAMESITE=none requires SESSION_COOKIE_SECURE=true.")
            if not self.session_cookie_path.startswith("/api/v1/auth"):
                warnings.append("SESSION_COOKIE_PATH should be scoped to /api/v1/auth in production.")
            if self.access_token_expire_minutes > 15:
                warnings.append("ACCESS_TOKEN_EXPIRE_MINUTES should be 15 or less in production.")
            if self.password_reset_token_expire_minutes <= 0 or self.password_reset_token_expire_minutes > 120:
                warnings.append("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES should be between 1 and 120 in production.")
            if not self.smtp_host or not self.smtp_from_email:
                warnings.append("SMTP_HOST and SMTP_FROM_EMAIL are required in production for password recovery email.")
            if self.rate_limits_enabled and self.rate_limit_backend.lower() not in {"redis", "gateway", "mongodb"}:
                warnings.append("RATE_LIMIT_BACKEND should use Redis or a gateway in production.")
        return warnings

    def public_runtime_info(self) -> dict:
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "environment": self.environment.value,
            "deployment_profile": self.deployment_profile.value,
            "database_engine": "mongodb",
            "scheduler_enabled": self.scheduler_enabled,
            "rate_limits_enabled": self.rate_limits_enabled,
            "rate_limit_backend": self.rate_limit_backend,
            "observability_enabled": self.observability_enabled,
            "worker_backend": self.worker_backend,
            "publishing_dry_run": self.publishing_dry_run,
            "app_base_url": self.app_base_url,
            "frontend_base_url": self.frontend_base_url,
            "api_public_url": self.api_public_url,
        }


settings = Settings()
settings.ensure_runtime_dirs()
