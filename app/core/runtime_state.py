"""Process-wide runtime flags shared across modules."""
from __future__ import annotations

_scheduler_active = False


def set_scheduler_active(active: bool) -> None:
    global _scheduler_active
    _scheduler_active = active


def is_scheduler_active() -> bool:
    return _scheduler_active
