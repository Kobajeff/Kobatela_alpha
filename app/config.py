"""Application configuration settings."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import AliasChoices, BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Runtime toggles -----------------------------------------------------
# Environnement d'exécution: "dev" | "staging" | "prod"
ENV = os.getenv("KOB_ENV", "dev").lower()

# Clé legacy (uniquement tolérée en DEV)
DEV_API_KEY = os.getenv("DEV_API_KEY") or os.getenv("API_KEY") or "dev-secret-key"
DEV_API_KEY_ALLOWED = ENV in {"dev", "local", "dev_local"}

# Scopes reconnus
API_SCOPES = {"sender", "support", "admin"}

# Scheduler (optionnel)
SCHEDULER_ENABLED = os.getenv("KOB_SCHEDULER_ENABLED", "0") in {
    "1",
    "true",
    "yes",
    "True",
    "YES",
}
SCHEDULER_CRON = os.getenv("KOB_SCHEDULER_CRON", "0 3 * * *")


class Settings(BaseSettings):
    """Environment configuration for the Kobatella backend."""

    app_env: str = ENV
    database_url: str = "sqlite:///kobatella.db"
    psp_webhook_secret: str | None = None
    SECRET_KEY: str = "change-me"
    DEV_API_KEY: str | None = Field(
        default=DEV_API_KEY,
        validation_alias=AliasChoices("DEV_API_KEY", "API_KEY"),
    )
    CORS_ALLOW_ORIGINS: list[str] = [
        "https://kobatela.com",
        "https://app.kobatela.com",
        "http://localhost:3000",
    ]
    SENTRY_DSN: str | None = None
    PROMETHEUS_ENABLED: bool = True

    # --- AI Proof Advisor (MVP) ------------------------------------------
    AI_PROOF_ADVISOR_ENABLED: bool = False
    AI_PROOF_ADVISOR_PROVIDER: str = "openai"
    AI_PROOF_ADVISOR_MODEL: str = "gpt-5.1-mini"
    AI_PROOF_MAX_IMAGE_RESOLUTION_X: int = 1600
    AI_PROOF_MAX_IMAGE_RESOLUTION_Y: int = 1200
    AI_PROOF_MAX_PDF_PAGES: int = 5
    AI_PROOF_TIMEOUT_SECONDS: int = 12
    OPENAI_API_KEY: str | None = None

    # --- Invoice OCR -----------------------------------------------------
    INVOICE_OCR_ENABLED: bool = False
    INVOICE_OCR_PROVIDER: str = "none"
    INVOICE_OCR_API_KEY: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="", env_file_encoding="utf-8"
    )

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


__all__ = [
    "ENV",
    "DEV_API_KEY",
    "DEV_API_KEY_ALLOWED",
    "API_SCOPES",
    "SCHEDULER_ENABLED",
    "SCHEDULER_CRON",
    "Settings",
    "AppInfo",
    "settings",
    "get_settings",
]
