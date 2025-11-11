"""Database configuration and session management."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models.base import Base

# Public aliases kept for backward compatibility with older imports.
engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def _engine_kwargs() -> dict[str, object]:
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


def init_engine() -> Engine:
    """Initialise the synchronous SQLAlchemy engine lazily."""

    global engine, SessionLocal
    if engine is None:
        settings = get_settings()
        engine = create_engine(settings.database_url, future=True, echo=False, **_engine_kwargs())
        SessionLocal = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return engine


def get_engine() -> Engine:
    """Return the active SQLAlchemy engine, creating it if necessary."""

    if engine is None:
        return init_engine()
    return engine


def get_sessionmaker() -> sessionmaker[Session]:
    """Return the configured session factory, initialising the engine on demand."""

    if SessionLocal is None:
        init_engine()
    assert SessionLocal is not None  # for type-checkers
    return SessionLocal


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # pragma: no cover - defensive
    """Ensure SQLite enforces foreign key constraints."""

    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        # Some DBAPI implementations (e.g. tests with in-memory DBs) might not support PRAGMA.
        pass


def create_all() -> None:
    """Create all database tables using the shared declarative metadata."""

    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def close_engine() -> None:
    """Dispose of the SQLAlchemy engine and reset the session factory."""

    global engine, SessionLocal
    if engine is not None:
        engine.dispose()
        engine = None
        SessionLocal = None


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for FastAPI dependencies."""

    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "create_all",
    "get_db",
    "get_engine",
    "get_sessionmaker",
    "init_engine",
    "close_engine",
]
