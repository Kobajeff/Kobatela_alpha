"""Database lifecycle helpers."""
# app/core/database.py
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from typing import Optional

from app.config import get_settings

Base = declarative_base()
engine = None  # sera initialisé par init_engine()
SessionLocal: Optional[sessionmaker] = None


def _get_database_url() -> str:
    settings = get_settings()
    return getattr(settings, "DATABASE_URL",
           getattr(settings, "database_url", "sqlite:///./kobatela.db"))


def init_engine() -> None:
    """Initialise le moteur et la Session factory (sync engine pour tests & alembic)."""
    global engine, SessionLocal
    if engine is None:
        engine = create_engine(_get_database_url(), future=True)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def close_engine() -> None:
    """Ferme proprement le moteur."""
    global engine
    if engine is not None:
        engine.dispose()
        engine = None


__all__ = ["Base", "engine", "SessionLocal", "init_engine", "close_engine"]

