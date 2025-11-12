"""API key generation and validation helpers."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.api_key import ApiKey


def hash_key(raw: str) -> str:
    """Return an HMAC-SHA256 hash for the provided API key."""

    return hmac.new(settings.SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()


def gen_key(prefix_len: int = 6) -> tuple[str, str, str]:
    """Generate a user-facing API key, its prefix, and the stored hash."""

    prefix = "koba_" + secrets.token_hex(prefix_len)[:prefix_len]
    suffix = secrets.token_urlsafe(32)
    raw = f"{prefix}.{suffix}"
    return raw, prefix, hash_key(raw)


def find_valid_key(db: Session, raw_or_dev: str) -> Optional[ApiKey | str]:
    """Return a matching active API key or the legacy token identifier."""

    if settings.DEV_API_KEY and secrets.compare_digest(raw_or_dev, settings.DEV_API_KEY):
        return "legacy"

    key_hash = hash_key(raw_or_dev)
    key = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        .first()
    )
    if key and (not key.expires_at or key.expires_at > datetime.now(UTC)):
        return key
    return None
