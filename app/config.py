"""Application configuration settings."""
from functools import lru_cache

from pydantic import AliasChoices, BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment configuration for the Kobatella backend."""

    app_env: str = "dev"
    database_url: str = "sqlite:///kobatella.db"
    psp_webhook_secret: str | None = None
    SECRET_KEY: str = "change-me"
    DEV_API_KEY: str | None = Field(
        default="koba_jeff",
        validation_alias=AliasChoices("DEV_API_KEY", "API_KEY"),
    )
    CORS_ALLOW_ORIGINS: list[str] = [
        "https://kobatela.com",
        "https://app.kobatela.com",
        "http://localhost:3000",
    ]
    SENTRY_DSN: str | None = None
    PROMETHEUS_ENABLED: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", env_file_encoding="utf-8")

    @field_validator("psp_webhook_secret")
    @classmethod
    def _strip_empty_secret(cls, value: str | None) -> str | None:
        """Normalise empty webhook secrets to ``None`` for easier validation."""

        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class AppInfo(BaseModel):
    name: str = "kobatella-backend"
    version: str = "0.1.0"


settings = Settings()


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return settings
