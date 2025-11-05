"""Idempotency helpers."""
from typing import Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

T = TypeVar("T")


def get_existing_by_key(db: Session, model: Type[T], key_value: str, *, key_field: str = "idempotency_key") -> Optional[T]:
    """Return existing record for a given idempotency key if present."""

    column = getattr(model, key_field)
    stmt = select(model).where(column == key_value)
    return db.scalars(stmt).first()
