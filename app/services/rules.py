"""Rule engine helpers for proof validation."""
import logging
from datetime import datetime, UTC
from math import radians, sin, cos, asin, sqrt
from typing import Any

logger = logging.getLogger(__name__)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance en mètres entre deux points GPS (formule de Haversine)."""
    R = 6371000.0  # rayon moyen de la Terre en mètres
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def validate_photo_metadata(
    *, metadata: dict[str, Any], geofence: tuple[float, float, float] | None, max_skew_minutes: int = 120
) -> tuple[bool, str | None]:
    """
    Valide les métadonnées EXIF et GPS d'une photo.
    Retourne (ok, raison_si_invalide).

    Règles :
      - Le timestamp EXIF doit exister et être dans la fenêtre temporelle autorisée.
      - Si une géofence est fournie, les coordonnées GPS doivent être dans le rayon.
      - La source doit être "app" ou "camera".
    """
    ts = metadata.get("exif_timestamp")
    lat = metadata.get("gps_lat")
    lng = metadata.get("gps_lng")
    source = (metadata.get("source") or "").lower()

    # Vérif timestamp EXIF
    try:
        ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
    except Exception:
        ts_dt = None

    now = datetime.now(tz=UTC)
    if not ts_dt or abs((now - ts_dt).total_seconds()) > max_skew_minutes * 60:
        logger.info("Photo failed time skew check", extra={"reason": "TIME_SKEW_OR_MISSING_EXIF"})
        return False, "TIME_SKEW_OR_MISSING_EXIF"

    # Vérif géofence
    if geofence is not None:
        if lat is None or lng is None:
            logger.info("Missing GPS for geofence", extra={"reason": "MISSING_GPS"})
            return False, "MISSING_GPS"
        lat0, lng0, radius_m = geofence
        dist = _haversine_m(float(lat0), float(lng0), float(lat), float(lng))
        if dist > float(radius_m):
            logger.info("Photo outside geofence", extra={"reason": "OUT_OF_GEOFENCE", "distance_m": dist})
            return False, "OUT_OF_GEOFENCE"

    # Vérif source
    if source not in ("camera", "app"):
        logger.info("Untrusted source", extra={"reason": "UNTRUSTED_SOURCE", "source": source})
        return False, "UNTRUSTED_SOURCE"

    return True, None


__all__ = ["validate_photo_metadata"]

