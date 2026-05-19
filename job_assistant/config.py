import os
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Environment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class Settings(BaseSettings):
    environment: Environment = Environment(os.getenv("ENVIRONMENT", "dev"))

    app_name: str = "Job Application Assistant"
    app_version: str = "1.0.0"

    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    streamlit_port: int = int(os.getenv("STREAMLIT_PORT", "8501"))

    db_path: str = os.getenv("APP_DB_PATH", "data/job_assistant.sqlite3")
    database_url: Optional[str] = os.getenv("DATABASE_URL")

    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4-turbo")

    google_credentials_file: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    google_token_file: str = os.getenv("GOOGLE_TOKEN_FILE", "token.json")

    scheduler_enabled: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"

    log_level: str = os.getenv("LOG_LEVEL", "INFO" if os.getenv("ENVIRONMENT") == "prod" else "DEBUG")
    log_file: Optional[str] = os.getenv("LOG_FILE", "logs/job_assistant.log" if os.getenv("ENVIRONMENT") == "prod" else None)

    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-prod")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    stripe_secret_key: Optional[str] = os.getenv("STRIPE_SECRET_KEY")
    stripe_publishable_key: Optional[str] = os.getenv("STRIPE_PUBLISHABLE_KEY")

    sendgrid_api_key: Optional[str] = os.getenv("SENDGRID_API_KEY")
    sendgrid_from_email: str = os.getenv("SENDGRID_FROM_EMAIL", "noreply@jobassistant.io")

    max_upload_size_mb: int = 10
    max_jobs_per_user_free: int = 50
    max_jobs_per_user_premium: int = 500

    cors_origins: list[str] = ["*"]

    class Config:
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PROD

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEV


settings = Settings()
