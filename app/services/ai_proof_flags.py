"""Helper utilities for AI Proof Advisor feature flags."""

from app.config import get_settings


def _current_settings():
    return get_settings()


def ai_enabled() -> bool:
    """Return True if the AI Proof Advisor is enabled in settings."""

    return bool(_current_settings().AI_PROOF_ADVISOR_ENABLED)


def ai_model() -> str:
    """Return the AI model used for proof analysis."""

    return _current_settings().AI_PROOF_ADVISOR_MODEL


def ai_provider() -> str:
    """Return the AI provider (e.g., 'openai', 'mock')."""

    return _current_settings().AI_PROOF_ADVISOR_PROVIDER


def ai_timeout_seconds() -> int:
    """Return the maximum timeout for AI calls, in seconds."""

    return int(_current_settings().AI_PROOF_TIMEOUT_SECONDS)
