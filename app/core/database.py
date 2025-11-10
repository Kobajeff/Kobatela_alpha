"""Compatibility layer re-exporting shared database helpers."""
from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import db

# Re-exported symbols to keep historic import paths working.
Base = db.Base
engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def init_engine() -> Engine:
    """Initialise the database engine and keep local aliases in sync."""

    global engine, SessionLocal
    engine = db.init_engine()
    SessionLocal = db.SessionLocal
    return engine


def close_engine() -> None:
    """Dispose of the shared database engine and reset aliases."""

    global engine, SessionLocal
    db.close_engine()
    engine = None
    SessionLocal = None


__all__ = ["Base", "engine", "SessionLocal", "init_engine", "close_engine"]
