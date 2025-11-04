from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import require_api_key
"""Endpoints for spend usage and purchases."""
import logging

from fastapi import APIRouter, Depends, Header, status
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
from app.services import spend as spend_service

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
from app.security import require_api_key
from app.services.spend import allow_usage, create_category, create_merchant, create_purchase

router = APIRouter(prefix="/spend", tags=["spend"], dependencies=[Depends(require_api_key)])
logger = logging.getLogger(__name__)


@router.post("/categories", response_model=SpendCategoryRead, status_code=status.HTTP_201_CREATED)
def post_category(payload: SpendCategoryCreate, db: Session = Depends(get_db)) -> SpendCategoryRead:
    """Create a spend category."""

    category = create_category(db, payload)
    return category


@router.post("/merchants", response_model=MerchantRead, status_code=status.HTTP_201_CREATED)
def post_merchant(payload: MerchantCreate, db: Session = Depends(get_db)) -> MerchantRead:
    """Create a merchant."""

    merchant = create_merchant(db, payload)
    return merchant


@router.post("/allow", status_code=status.HTTP_201_CREATED)
def post_allowed_usage(payload: AllowedUsageCreate, db: Session = Depends(get_db)) -> dict[str, str]:
    """Allow usage for a merchant or category."""

    return allow_usage(db, payload)


@router.post("/purchases", response_model=PurchaseRead, status_code=status.HTTP_201_CREATED)
def post_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> PurchaseRead:
    """Create a purchase if authorized."""

    purchase = create_purchase(db, payload, idempotency_key=idempotency_key)
    return purchase
