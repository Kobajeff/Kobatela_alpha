from decimal import Decimal

from app.services.document_checks import compute_document_backend_checks


def test_amount_checks_use_decimal_precision():
    requirements = {"expected_amount": "100.10", "expected_currency": "usd"}
    metadata = {"invoice_total_amount": "100.10", "invoice_currency": "USD"}

    checks = compute_document_backend_checks(proof_requirements=requirements, metadata=metadata)
    amount_check = checks["amount_check"]

    assert amount_check["amount_match"] is True
    assert amount_check["currency_match"] is True
    assert amount_check["absolute_diff"] == "0.00"


def test_amount_checks_detect_difference():
    requirements = {"expected_amount": Decimal("90.00"), "expected_currency": "EUR"}
    metadata = {"invoice_total_amount": "120.50", "invoice_currency": "eur"}

    checks = compute_document_backend_checks(proof_requirements=requirements, metadata=metadata)
    amount_check = checks["amount_check"]

    assert amount_check["amount_match"] is False
    assert amount_check["currency_match"] is True
    assert amount_check["absolute_diff"] == "30.50"
