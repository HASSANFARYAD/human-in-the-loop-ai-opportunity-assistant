import os
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import field_validator
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
    app_base_url: str = os.getenv("APP_BASE_URL", "http://localhost:8501")
    api_public_url: str = os.getenv("API_PUBLIC_URL", "http://localhost:8000")

    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    streamlit_port: int = int(os.getenv("STREAMLIT_PORT", "8501"))

    app_data_dir: str = os.getenv("APP_DATA_DIR", "data")
    log_dir: str = os.getenv("LOG_DIR", "logs")
    db_path: str = os.getenv("APP_DB_PATH", str(Path(os.getenv("APP_DATA_DIR", "data")) / "job_assistant.sqlite3"))
    database_url: Optional[str] = os.getenv("DATABASE_URL")

    # User-owned provider API keys are stored encrypted in the database from the Integrations UI.
    # Env provider keys are intentionally not part of normal user workflows.
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    default_ai_provider: str = os.getenv("DEFAULT_AI_PROVIDER", "openai")

    google_credentials_file: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    google_token_file: str = os.getenv("GOOGLE_TOKEN_FILE", "token.json")

    scheduler_enabled: bool = _bool_env("SCHEDULER_ENABLED", True)
    rate_limits_enabled: bool = _bool_env("RATE_LIMITS_ENABLED", True)
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
    rate_limit_ai_per_hour: int = int(os.getenv("RATE_LIMIT_AI_PER_HOUR", "60"))
    rate_limit_feedback_per_hour: int = int(os.getenv("RATE_LIMIT_FEEDBACK_PER_HOUR", "20"))
    rate_limit_publish_per_hour: int = int(os.getenv("RATE_LIMIT_PUBLISH_PER_HOUR", "20"))
    rate_limit_backend: str = os.getenv("RATE_LIMIT_BACKEND", "sqlite")
    redis_url: Optional[str] = os.getenv("REDIS_URL")

    observability_enabled: bool = _bool_env("OBSERVABILITY_ENABLED", True)
    tracing_enabled: bool = _bool_env("TRACING_ENABLED", True)
    metrics_retention_days: int = int(os.getenv("METRICS_RETENTION_DAYS", "14"))
    error_alert_threshold_per_hour: int = int(os.getenv("ERROR_ALERT_THRESHOLD_PER_HOUR", "10"))
    latency_alert_threshold_ms: int = int(os.getenv("LATENCY_ALERT_THRESHOLD_MS", "3000"))

    worker_backend: str = os.getenv("WORKER_BACKEND", "sqlite")
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

    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-prod")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))
    refresh_token_expire_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "job_assistant_refresh")
    session_cookie_secure: bool = _bool_env("SESSION_COOKIE_SECURE", os.getenv("ENVIRONMENT", "dev") == "prod")
    app_encryption_key: Optional[str] = os.getenv("APP_ENCRYPTION_KEY")

    max_upload_size_mb: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    max_jobs_per_user_free: int = int(os.getenv("MAX_JOBS_PER_USER_FREE", "50"))
    max_jobs_per_user_premium: int = int(os.getenv("MAX_JOBS_PER_USER_PREMIUM", "500"))

    cors_origins: list[str] = ["*"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        raw = os.getenv("CORS_ORIGINS")
        if raw:
            return [item.strip() for item in raw.split(",") if item.strip()]
        return value

    class Config:
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PROD

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEV

    @property
    def effective_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.db_path}"

    def ensure_runtime_dirs(self) -> None:
        Path(self.app_data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)
        if self.log_file:
            Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)

    def startup_warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.is_production:
            if not self.app_encryption_key:
                warnings.append("APP_ENCRYPTION_KEY is required in production for encrypted user provider keys.")
            if self.jwt_secret_key in {"dev-secret-key-change-in-prod", "change-me-before-production", ""}:
                warnings.append("JWT_SECRET_KEY must be changed before production use.")
            if "*" in self.cors_origins:
                warnings.append("CORS_ORIGINS should be restricted in production.")
            if not self.session_cookie_secure:
                warnings.append("SESSION_COOKIE_SECURE should be true behind HTTPS in production.")
        return warnings

    def public_runtime_info(self) -> dict:
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "environment": self.environment.value,
            "deployment_profile": self.deployment_profile.value,
            "database_engine": "postgresql" if (self.database_url or "").startswith("postgres") else "sqlite",
            "scheduler_enabled": self.scheduler_enabled,
            "rate_limits_enabled": self.rate_limits_enabled,
            "rate_limit_backend": self.rate_limit_backend,
            "observability_enabled": self.observability_enabled,
            "worker_backend": self.worker_backend,
            "publishing_dry_run": self.publishing_dry_run,
            "app_base_url": self.app_base_url,
            "api_public_url": self.api_public_url,
        }


settings = Settings()
settings.ensure_runtime_dirs()
