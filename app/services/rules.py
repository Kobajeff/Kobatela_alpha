"""Rule engine helpers for proof validation."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone ,UTC
from enum import Enum
from typing import Any

from app.models.milestone import Milestone
from app.utils.geo import haversine_m
from app.utils.time import parse_iso_utc
from math import asin, cos, radians, sin, sqrt

logger = logging.getLogger(__name__)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in meters between two latitude/longitude points."""

    r_earth = 6_371_000.0
    p = radians
    dlat = p(lat2 - lat1)
    dlon = p(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(p(lat1)) * cos(p(lat2)) * sin(dlon / 2) ** 2
    return 2 * r_earth * asin(sqrt(a))


def validate_photo_metadata(
    *, metadata: dict, geofence: tuple[float, float, float] | None, max_skew_minutes: int = 120
) -> tuple[bool, str | None]:
    """Validate EXIF metadata for a photo proof.

    Returns a tuple ``(ok, reason_if_not_ok)``.
    """

    ts = metadata.get("exif_timestamp")
    lat = metadata.get("gps_lat")
    lng = metadata.get("gps_lng")
    source = metadata.get("source")

    try:
        ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
    except Exception:  # pragma: no cover - defensive against malformed timestamps
        ts_dt = None

    now = datetime.now(tz=UTC)
    if not ts_dt or abs((now - ts_dt).total_seconds()) > max_skew_minutes * 60:
        logger.info("Photo metadata failed time skew validation", extra={"reason": "TIME_SKEW_OR_MISSING_EXIF"})
        return False, "TIME_SKEW_OR_MISSING_EXIF"

    if geofence is not None:
        if lat is None or lng is None:
            logger.info("Photo metadata missing GPS for geofence", extra={"reason": "MISSING_GPS"})
            return False, "MISSING_GPS"
        lat0, lng0, radius_m = geofence
        dist = _haversine_m(lat0, lng0, float(lat), float(lng))
        if dist > float(radius_m):
            logger.info(
                "Photo metadata outside geofence",
                extra={"reason": "OUT_OF_GEOFENCE", "distance_m": dist, "radius_m": radius_m},
            )
            return False, "OUT_OF_GEOFENCE"

    if source not in ("camera", "app"):
        logger.info("Photo metadata has untrusted source", extra={"reason": "UNTRUSTED_SOURCE", "source": source})
        return False, "UNTRUSTED_SOURCE"

    return True, None


__all__ = ["_haversine_m", "validate_photo_metadata"]
