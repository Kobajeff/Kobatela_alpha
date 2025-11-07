"""Rule engine helpers for proof validation."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, UTC
from typing import Optional, Tuple, Dict, Any

from app.models.milestone import Milestone
from app.utils.geo import haversine_m
from app.utils.time import parse_iso_utc

logger = logging.getLogger(__name__)


def validate_photo_metadata(
    *,
    metadata: dict[str, Any],
    milestone: Milestone | None = None,
    geofence: Optional[Tuple[float, float, float]] = None,
    max_age_minutes: int = 10,
    future_tolerance_minutes: int = 2,
    geofence_tolerance_m: float = 15.0,
) ->  tuple [bool, Optional[str]]:
    """
    Valide les métadonnées EXIF/GPS d'une photo.
    Retourne (ok, reason_code|None).

    Règles / reason codes :
      - MISSING_EXIF_TIMESTAMP : pas d'horodatage valide
      - STALE_TIMESTAMP        : photo trop ancienne (> max_age_minutes)
      - FUTURE_TIMESTAMP       : datée trop dans le futur (> future_tolerance_minutes)
      - MISSING_GPS            : GPS absent alors qu'une géofence existe
      - OUT_OF_GEOFENCE        : hors zone autorisée (rayon + tolérance)
      - UNTRUSTED_SOURCE       : source non autorisée (autorisé: app, camera)
    """
    ts_raw = metadata.get("exif_timestamp")
    gps_lat = metadata.get("gps_lat")
    gps_lng = metadata.get("gps_lng")
    source = (metadata.get("source") or "").strip().lower()

    # --- Timestamp EXIF
    try:
        ts = parse_iso_utc(ts_raw) if ts_raw else None
    except Exception:
        ts = None

    if not ts:
        logger.info("Photo missing EXIF timestamp", extra={"reason": "MISSING_EXIF_TIMESTAMP"})
        return False, "MISSING_EXIF_TIMESTAMP"

    now = datetime.now(UTC)
    age = now - ts  # >0 si passé, <0 si futur

    if age > timedelta(minutes=max_age_minutes):
        logger.info(
            "Photo too old",
            extra={"reason": "STALE_TIMESTAMP", "age_seconds": age.total_seconds(), "max_age_minutes": max_age_minutes},
        )
        return False, "STALE_TIMESTAMP"

    if age < timedelta(0) and (-age) > timedelta(minutes=future_tolerance_minutes):
        logger.info(
            "Photo timestamp too far in the future",
            extra={
                "reason": "FUTURE_TIMESTAMP",
                "skew_seconds": (-age).total_seconds(),
                "tolerance_minutes": future_tolerance_minutes,
            },
        )
        return False, "FUTURE_TIMESTAMP"

    # --- Géofence (si définie sur le milestone)
    if milestone and milestone.geofence_lat is not None and milestone.geofence_lng is not None and milestone.geofence_radius_m is not None:
        if gps_lat is None or gps_lng is None:
            logger.info("Missing GPS for geofence", extra={"reason": "MISSING_GPS"})
            return False, "MISSING_GPS"

        try:
            distance = haversine_m(
                float(milestone.geofence_lat),
                float(milestone.geofence_lng),
                float(gps_lat),
                float(gps_lng),
            )
        except Exception:
            logger.info("GPS parsing error -> treat as missing GPS", extra={"reason": "MISSING_GPS"})
            return False, "MISSING_GPS"

        allowed = float(milestone.geofence_radius_m) + float(geofence_tolerance_m)
        if distance > allowed:
            logger.info(
                "Outside geofence",
                extra={
                    "reason": "OUT_OF_GEOFENCE",
                    "distance_m": distance,
                    "radius_m": float(milestone.geofence_radius_m),
                    "tolerance_m": float(geofence_tolerance_m),
                },
            )
            return False, "OUT_OF_GEOFENCE"

    # --- Source
    if source and source not in {"app", "camera"}:
        logger.info("Untrusted source", extra={"reason": "UNTRUSTED_SOURCE", "source": source})
        return False, "UNTRUSTED_SOURCE"

    return True, None


__all__ = ["validate_photo_metadata"]

