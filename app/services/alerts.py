"""Alert service helpers."""
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.alert import Alert

logger = logging.getLogger(__name__)


def create_alert(db: Session, *, alert_type: str, message: str, actor_user_id: int | None, payload: dict[str, Any]) -> Alert:
    """Persist an alert in the database."""

    alert = Alert(type=alert_type, message=message, actor_user_id=actor_user_id, payload_json=payload)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    logger.warning("Alert created", extra={"type": alert_type, "payload": payload})
    return alert
