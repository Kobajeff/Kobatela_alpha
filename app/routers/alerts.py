"""Alerts endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.alert import Alert
from app.schemas.alert import AlertRead
from app.security import require_api_key

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[AlertRead])
def list_alerts(alert_type: str | None = Query(default=None, alias="type"), db: Session = Depends(get_db)) -> list[Alert]:
    stmt = select(Alert)
    if alert_type:
        stmt = stmt.where(Alert.type == alert_type)
    return list(db.scalars(stmt).all())
