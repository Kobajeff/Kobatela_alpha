"""Database lifecycle helpers."""
from __future__ import annotations

from sqlalchemy.engine import Engine

from app import models
from app.db import engine


async def init_engine() -> None:
    """Initialize database connections and ensure schema is ready."""

    models.Base.metadata.create_all(bind=engine)


async def close_engine() -> None:
    """Dispose of active database connections."""

    if isinstance(engine, Engine):
        engine.dispose()
