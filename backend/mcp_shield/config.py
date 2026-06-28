from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    proxy_host: str = "0.0.0.0"
    proxy_port: int = 8001

    target_host: str = "127.0.0.1"
    target_port: int = 8000

    @property
    def target_base_url(self) -> str:
        return f"http://{self.target_host}:{self.target_port}"

    events_db_path: str = "data/mcp_shield_events.db"

    injection_sensitivity: float = 1.0

    approved_outbound_domains: list[str] = [
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
        "api.x.ai",
        "api.groq.com",
    ]

    max_ai_calls_per_user_per_hour: int = 50

    allowed_data_directory: str = "data"

    request_timeout_seconds: int = 120
    stream_timeout_seconds: int = 300

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file="backend/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
