"""Application configuration settings."""
from functools import lru_cache
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment configuration for the Kobatella backend."""

    app_env: str = "dev"
    database_url: str = "sqlite:///kobatella.db"
    api_key: str = "dev-secret-key"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", env_file_encoding="utf-8")


class AppInfo(BaseModel):
    name: str = "kobatella-backend"
    version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
