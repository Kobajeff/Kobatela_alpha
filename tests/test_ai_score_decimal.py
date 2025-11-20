from decimal import Decimal

from app.models.proof import Proof


def test_proof_ai_score_accepts_decimal_type():
    """Ensure Proof.ai_score is compatible with Decimal values."""
    proof = Proof()
    proof.ai_score = Decimal("0.731")

    assert isinstance(proof.ai_score, Decimal)
    assert proof.ai_score == Decimal("0.731")
