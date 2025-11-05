"""Payment execution endpoints."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.payment import PaymentRead
from app.security import require_api_key
from app.services import payments as payments_service

router = APIRouter(prefix="/payments", tags=["payments"], dependencies=[Depends(require_api_key)])


@router.post("/execute/{payment_id}", response_model=PaymentRead, status_code=status.HTTP_200_OK)
def execute_payment(payment_id: int, db: Session = Depends(get_db)):
    """Execute a pending payment."""

    return payments_service.execute_payment(db, payment_id)
