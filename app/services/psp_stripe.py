"""Stripe SDK wrapper for payment and payout operations."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict

import stripe

from app.config import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover - hints only
    from app.models import EscrowAgreement, Payment, User


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

    def _ensure_connect_enabled(self) -> None:
        if not self._connect_enabled:
            raise RuntimeError(
                "Stripe Connect is disabled; enable STRIPE_CONNECT_ENABLED to create connected accounts or transfers."
            )

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

    def create_connected_account(self, user: "User") -> stripe.Account:
        """Create a Stripe Connect Express account using the user's details where available.

        Falls back to ``FR`` as the country when none is provided and requests transfers
        capability for payouts.
        """

        self._ensure_connect_enabled()

        email = getattr(user, "email", None)
        country = getattr(user, "country", None) or "FR"

        return stripe.Account.create(
            type="express",
            country=country,
            email=email,
            capabilities={"transfers": {"requested": True}},
            metadata={"user_id": str(getattr(user, "id", ""))},
        )

    def create_account_link(self, account_id: str) -> stripe.AccountLink:
        """Create an onboarding account link for a connected account using placeholder URLs."""

        self._ensure_connect_enabled()

        refresh_url = "https://app.kobatela.com/stripe/onboarding/refresh"
        return_url = "https://app.kobatela.com/stripe/onboarding/return"

        return stripe.AccountLink.create(
            account=account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
        )

    def create_transfer_to_connected(
        self,
        *,
        escrow: "EscrowAgreement",
        payment: "Payment",
        destination_account_id: str,
        amount: Decimal,
        currency: str,
    ) -> stripe.Transfer:
        """Create a Transfer from the platform balance to a connected account.

        The ``amount`` is expressed in major units and is converted to the smallest
        unit for Stripe. Metadata includes escrow, payment, and optional milestone
        identifiers for traceability.
        """

        self._ensure_connect_enabled()

        metadata: Dict[str, Any] = {
            "escrow_id": str(escrow.id),
            "payment_id": str(payment.id),
        }

        if getattr(payment, "milestone_id", None) is not None:
            metadata["milestone_id"] = str(payment.milestone_id)

        return stripe.Transfer.create(
            amount=_to_cents(amount),
            currency=currency,
            destination=destination_account_id,
            metadata=metadata,
        )
