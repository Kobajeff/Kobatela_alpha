"""Centralized logging helpers for the Kobatella backend."""
from __future__ import annotations

import logging
from typing import Optional

from pythonjsonlogger import jsonlogger


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging with a JSON formatter."""

    root_logger = logging.getLogger()
    # Remove existing handlers to avoid duplicate logs when reloading.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    root_logger.setLevel(level.upper())

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s %(extra)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Return a logger configured with the shared root settings."""

    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level.upper())
    return logger


__all__ = ["setup_logging", "get_logger"]
