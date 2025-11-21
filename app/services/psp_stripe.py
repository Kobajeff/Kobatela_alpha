"""Stripe SDK wrapper for payment and payout operations."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict

import stripe

from app.config import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover - hints only
    from app.models import EscrowAgreement, Payment


def _to_cents(amount: Decimal) -> int:
    """Convert a decimal amount to the smallest currency unit expected by Stripe."""

    normalized = Decimal(str(amount)).quantize(Decimal("0.01"))
    return int((normalized * 100).to_integral_value())


class StripeClient:
    """Wrapper around the Stripe Python SDK to isolate PSP concerns."""

    def __init__(self, settings: Settings) -> None:
        """Initialise the client and set the API key when enabled."""

        self.settings = settings
        self._ensure_enabled()
        self._secret_key = settings.STRIPE_SECRET_KEY
        self._webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        self._connect_enabled = bool(settings.STRIPE_CONNECT_ENABLED)

        if not self._secret_key:
            raise RuntimeError("Stripe secret key is missing; configure STRIPE_SECRET_KEY.")

        stripe.api_key = self._secret_key

    @classmethod
    def from_env(cls) -> "StripeClient":
        """Instantiate a client using the cached application settings."""

        return cls(get_settings())

    def _ensure_enabled(self) -> None:
        if not self.settings.STRIPE_ENABLED:
            raise RuntimeError("Stripe integration is disabled; enable STRIPE_ENABLED to proceed.")

    def create_funding_payment_intent(
        self, escrow: "EscrowAgreement", amount: Decimal, currency: str
    ) -> stripe.PaymentIntent:
        """Create a PaymentIntent used to fund an escrow."""

        metadata: Dict[str, Any] = {"escrow_id": str(escrow.id)}
        for optional_key in ("mandate_id", "usage_mandate_id"):
            optional_value = getattr(escrow, optional_key, None)
            if optional_value is not None:
                metadata[optional_key] = str(optional_value)

        return stripe.PaymentIntent.create(
            amount=_to_cents(amount),
            currency=currency,
            metadata=metadata,
        )

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> stripe.Event:
        """Verify and construct a Stripe webhook event."""

        if not self._webhook_secret:
            raise RuntimeError(
                "Stripe webhook secret is missing; configure STRIPE_WEBHOOK_SECRET for verification."
            )

        return stripe.Webhook.construct_event(payload, sig_header, self._webhook_secret)

    def create_transfer_to_connected(
        self,
        *,
        escrow: "EscrowAgreement",
        payment: "Payment",
        destination_account_id: str,
        amount: Decimal,
        currency: str,
    ) -> stripe.Transfer:
        """Create a transfer to a connected account for a payout."""

        if not self._connect_enabled:
            raise RuntimeError(
                "Stripe Connect is disabled; enable STRIPE_CONNECT_ENABLED to create transfers."
            )

        metadata: Dict[str, Any] = {
            "escrow_id": str(escrow.id),
            "payment_id": str(payment.id),
        }

        return stripe.Transfer.create(
            amount=_to_cents(amount),
            currency=currency,
            destination=destination_account_id,
            metadata=metadata,
        )
