# app/services/idempotency.py
"""Idempotency helpers."""
from typing import Optional, Type, TypeVar, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

T = TypeVar("T")


def get_existing_by_key(
    db: Session,
    model: Type[T],
    key_value: str | None,
    *,
    key_field: str = "idempotency_key",
) -> Optional[T]:
    """Return existing record for a given idempotency key if present."""
    if not key_value:  # None, "", etc.
        return None
    if not hasattr(model, key_field):
        raise AttributeError(f"{model.__name__} has no field '{key_field}'")

    column = getattr(model, key_field)
    stmt = select(model).where(column == key_value).limit(1)
    return db.scalars(stmt).first()


def get_or_create_idempotent(
    db: Session,
    model: Type[T],
    key_value: str,
    build_instance: Callable[[], T],  # → ex: lambda: Payment(...)
    *,
    key_field: str = "idempotency_key",
) -> T:
    """Try to get an existing record by idempotency key, or create it atomically."""
    existing = get_existing_by_key(db, model, key_value, key_field=key_field)
    if existing:
        return existing
    instance = build_instance()
    try:
        db.add(instance)
        db.commit()
        db.refresh(instance)
        return instance
    except IntegrityError:
        db.rollback()
        # Course condition → re-read existing
        return get_existing_by_key(db, model, key_value, key_field=key_field)
