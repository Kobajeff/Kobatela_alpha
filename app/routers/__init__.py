"""API routers for the Kobatella backend."""
from fastapi import APIRouter

from . import alerts, escrow, health, transactions, users, spend, proofs, payments
from . import alerts, escrow, health, transactions, users, spend
from . import alerts, escrow, health, transactions, users


def get_api_router() -> APIRouter:
    """Return the root API router."""

    api_router = APIRouter()
    api_router.include_router(health.router)
    api_router.include_router(users.router)
    api_router.include_router(transactions.router)
    api_router.include_router(escrow.router)
    api_router.include_router(alerts.router)
    api_router.include_router(spend.router)
    api_router.include_router(proofs.router)
    api_router.include_router(payments.router)
    return api_router
