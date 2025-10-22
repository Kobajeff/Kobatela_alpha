"""Database configuration and session management."""
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings


def _engine_kwargs() -> dict[str, object]:
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


engine = create_engine(get_settings().database_url, future=True, echo=False, **_engine_kwargs())


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Ensure SQLite enforces foreign key constraints."""

    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        # If the connection does not support PRAGMA statements we ignore the failure.
        pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for FastAPI dependencies."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
