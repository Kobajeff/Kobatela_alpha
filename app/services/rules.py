"""Rule engine helpers for proof validation."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from app.models.milestone import Milestone
from app.utils.geo import haversine_m
from app.utils.time import parse_iso_utc

logger = logging.getLogger(__name__)


class Decision(str, Enum):
    """Possible outcomes for rule evaluation."""

    APPROVE = "APPROVE"
    PENDING = "PENDING"
    REJECT = "REJECT"


@dataclass(slots=True)
class RuleContext:
    """Holds tolerance parameters for rule evaluation."""

    max_photo_age: timedelta = timedelta(minutes=10)
    geofence_tolerance_m: float = 15.0
    trusted_sources: set[str] = field(default_factory=lambda: {"app"})


@dataclass(slots=True)
class ValidationResult:
    """Encapsulates the rule engine decision and reasons."""

    decision: Decision
    reasons: list[str] = field(default_factory=list)

    @property
    def is_approved(self) -> bool:
        return self.decision == Decision.APPROVE

    @property
    def is_pending(self) -> bool:
        return self.decision == Decision.PENDING

    @property
    def is_rejected(self) -> bool:
        return self.decision == Decision.REJECT


def validate_photo_metadata(
    *, metadata: dict[str, Any], milestone: Milestone, ctx: RuleContext | None = None
) -> ValidationResult:
    """Validate EXIF, GPS, and source hints for a photo proof."""

    ctx = ctx or RuleContext()
    reasons: list[str] = []

    timestamp_raw = metadata.get("exif_timestamp")
    try:
        timestamp = parse_iso_utc(timestamp_raw) if timestamp_raw else None
    except Exception:  # pragma: no cover - defensive against malformed input
        timestamp = None

    if timestamp is None:
        logger.info("Photo metadata missing or invalid timestamp", extra={"reason": "missing_or_bad_timestamp"})
        return ValidationResult(Decision.PENDING, ["missing_or_bad_timestamp"])

    now = datetime.now(timezone.utc)
    age = now - timestamp
    if age < timedelta(0) or age > ctx.max_photo_age:
        logger.info(
            "Photo metadata outside freshness window",
            extra={"reason": "stale_or_future_timestamp", "age_seconds": age.total_seconds()},
        )
        reasons.append("stale_or_future_timestamp")

    lat, lng, radius = milestone.geofence_lat, milestone.geofence_lng, milestone.geofence_radius_m
    gps_lat = metadata.get("gps_lat")
    gps_lng = metadata.get("gps_lng")

    if lat is not None and lng is not None and radius is not None:
        if gps_lat is None or gps_lng is None:
            logger.info("Photo metadata missing GPS for geofence", extra={"reason": "missing_gps_for_geofence"})
            reasons.append("missing_gps_for_geofence")
        else:
            distance = haversine_m(float(lat), float(lng), float(gps_lat), float(gps_lng))
            if distance > float(radius) + ctx.geofence_tolerance_m:
                logger.info(
                    "Photo metadata outside geofence",
                    extra={
                        "reason": "outside_geofence",
                        "distance_m": distance,
                        "radius_m": float(radius),
                        "tolerance_m": ctx.geofence_tolerance_m,
                    },
                )
                return ValidationResult(Decision.REJECT, ["outside_geofence"])

    source = (metadata.get("source") or "").strip().lower()
    if source and source not in ctx.trusted_sources:
        logger.info("Photo metadata from untrusted source", extra={"reason": "untrusted_source", "source": source})
        reasons.append("untrusted_source")

    if any(reason in {"stale_or_future_timestamp", "missing_gps_for_geofence", "untrusted_source"} for reason in reasons):
        return ValidationResult(Decision.PENDING, reasons)

    return ValidationResult(Decision.APPROVE, reasons)


__all__ = [
    "Decision",
    "RuleContext",
    "ValidationResult",
    "validate_photo_metadata",
]
