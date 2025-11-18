"""Backend document checks for AI advisory context."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional


def _parse_date(value: Any) -> Optional[date]:
    """Try to parse a date from a string 'YYYY-MM-DD'. Return None if invalid."""
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def compute_document_backend_checks(
    *,
    proof_requirements: Dict[str, Any] | None,
    metadata: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Compute backend checks for NON-PHOTO proofs (invoices, contracts, PDFs)."""

    proof_requirements = proof_requirements or {}
    metadata = metadata or {}

    checks: Dict[str, Any] = {
        "has_metadata": bool(metadata),
        "amount_check": None,
        "iban_check": None,
        "date_check": None,
        "supplier_check": None,
    }

    # -------- 1) AMOUNT / CURRENCY --------
    expected_amount = proof_requirements.get("expected_amount")
    expected_currency = proof_requirements.get("expected_currency")

    invoice_amount = metadata.get("invoice_amount")
    invoice_currency = metadata.get("invoice_currency")

    amount_check: Dict[str, Any] = {
        "expected_amount": expected_amount,
        "invoice_amount": invoice_amount,
        "absolute_diff": None,
        "relative_diff": None,
        "currency_expected": expected_currency,
        "currency_actual": invoice_currency,
        "currency_match": None,
    }

    if expected_amount is not None and invoice_amount is not None:
        try:
            ea = float(expected_amount)
            ia = float(invoice_amount)
            diff = ia - ea
            amount_check["absolute_diff"] = diff
            if ea != 0:
                amount_check["relative_diff"] = diff / ea
        except (TypeError, ValueError):
            pass

    if expected_currency and invoice_currency:
        amount_check["currency_match"] = (expected_currency == invoice_currency)

    checks["amount_check"] = amount_check

    # -------- 2) IBAN LAST4 --------
    expected_iban = (
        proof_requirements.get("expected_iban_last4")
        or proof_requirements.get("expected_iban")
    )
    if isinstance(expected_iban, str) and len(expected_iban) >= 4:
        expected_iban_last4 = expected_iban[-4:]
    else:
        expected_iban_last4 = None

    invoice_iban_last4 = metadata.get("iban_last4")

    iban_check: Dict[str, Any] = {
        "expected_iban_last4": expected_iban_last4,
        "invoice_iban_last4": invoice_iban_last4,
        "match": None,
    }

    if expected_iban_last4 and invoice_iban_last4:
        iban_check["match"] = (str(expected_iban_last4) == str(invoice_iban_last4))

    checks["iban_check"] = iban_check

    # -------- 3) DATE RANGE --------
    expected_date_min = proof_requirements.get("expected_date_min")
    expected_date_max = proof_requirements.get("expected_date_max")
    invoice_date_raw = metadata.get("invoice_date")

    d_min = _parse_date(expected_date_min)
    d_max = _parse_date(expected_date_max)
    d_inv = _parse_date(invoice_date_raw)

    date_check: Dict[str, Any] = {
        "expected_date_min": expected_date_min,
        "expected_date_max": expected_date_max,
        "invoice_date": invoice_date_raw,
        "in_range": None,
        "days_from_min": None,
        "days_from_max": None,
    }

    if d_inv is not None:
        if d_min is not None:
            date_check["days_from_min"] = (d_inv - d_min).days
        if d_max is not None:
            date_check["days_from_max"] = (d_inv - d_max).days

        if d_min is not None or d_max is not None:
            in_range = True
            if d_min is not None and d_inv < d_min:
                in_range = False
            if d_max is not None and d_inv > d_max:
                in_range = False
            date_check["in_range"] = in_range

    checks["date_check"] = date_check

    # -------- 4) SUPPLIER NAME --------
    expected_store = (
        proof_requirements.get("expected_store_name")
        or proof_requirements.get("expected_beneficiary")
    )
    supplier_name = metadata.get("supplier_name")

    supplier_check: Dict[str, Any] = {
        "expected_name": expected_store,
        "actual_name": supplier_name,
        "exact_match": None,
    }

    if expected_store and supplier_name:
        supplier_check["exact_match"] = (
            str(expected_store).strip().lower()
            == str(supplier_name).strip().lower()
        )

    checks["supplier_check"] = supplier_check

    return checks
