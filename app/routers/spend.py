"""Spending and usage endpoints."""
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.spend import (
    AllowedUsageCreate,
    MerchantCreate,
    MerchantRead,
    PurchaseCreate,
    PurchaseRead,
    SpendCategoryCreate,
    SpendCategoryRead,
)
from app.security import require_api_key
from app.services import spend as spend_service
from app.services import usage as usage_service

router = APIRouter(prefix="/spend", tags=["spend"], dependencies=[Depends(require_api_key)])


@router.post("/categories", response_model=SpendCategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload: SpendCategoryCreate, db: Session = Depends(get_db)):
    return spend_service.create_category(db, payload)


@router.post("/merchants", response_model=MerchantRead, status_code=status.HTTP_201_CREATED)
def create_merchant(payload: MerchantCreate, db: Session = Depends(get_db)):
    return spend_service.create_merchant(db, payload)


@router.post("/allow", status_code=status.HTTP_201_CREATED)
def allow_usage(payload: AllowedUsageCreate, db: Session = Depends(get_db)):
    return spend_service.allow_usage(db, payload)


@router.post("/purchases", response_model=PurchaseRead, status_code=status.HTTP_201_CREATED)
def create_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return spend_service.create_purchase(db, payload, idempotency_key=idempotency_key)


class AddPayeeIn(BaseModel):
    escrow_id: int
    payee_ref: str = Field(..., min_length=2, max_length=120)
    label: str = Field(..., min_length=2, max_length=200)
    daily_limit: Decimal | None = None
    total_limit: Decimal | None = None


@router.post("/allowed", status_code=status.HTTP_201_CREATED)
def add_allowed_payee(payload: AddPayeeIn, db: Session = Depends(get_db)):
    payee = usage_service.add_allowed_payee(
        db,
        escrow_id=payload.escrow_id,
        payee_ref=payload.payee_ref,
        label=payload.label,
        daily_limit=payload.daily_limit,
        total_limit=payload.total_limit,
    )
    return {
        "id": payee.id,
        "escrow_id": payee.escrow_id,
        "payee_ref": payee.payee_ref,
        "label": payee.label,
        "daily_limit": payee.daily_limit,
        "total_limit": payee.total_limit,
    }


class SpendIn(BaseModel):
    escrow_id: int
    payee_ref: str
    amount: Decimal
    note: str | None = None


@router.post("", status_code=status.HTTP_200_OK)
def spend(
    payload: SpendIn,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = idempotency_key or f"spend:{payload.escrow_id}:{payload.payee_ref}:{payload.amount:.2f}"
    payment = usage_service.spend_to_allowed_payee(
        db,
        escrow_id=payload.escrow_id,
        payee_ref=payload.payee_ref,
        amount=payload.amount,
        idempotency_key=key,
        note=payload.note,
    )
    return {
        "payment_id": payment.id,
        "escrow_id": payment.escrow_id,
        "amount": payment.amount,
        "status": payment.status.value,
        "psp_ref": payment.psp_ref,
    }
