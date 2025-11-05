# app/services/idempotency.py
"""Idempotency helpers."""
from typing import Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

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
