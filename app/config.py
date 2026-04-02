from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Receivables Copilot"
    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    default_timezone: str = "Asia/Kolkata"

    database_url: str = "sqlite:///./receivables_copilot.db"
    redis_url: str = "redis://localhost:6379/0"
    encryption_secret: str = "dev-secret"

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4.1-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = ""
    openrouter_app_name: str = "Receivables Copilot"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""

    confirmation_ttl_minutes: int = 20
    default_stale_days: int = 7
    default_follow_up_hour: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
