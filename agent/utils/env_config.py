"""Tiny helpers for reading typed env vars with safe fallbacks.

Logs a warning and falls back to the default if the env var is set but
unparseable, so a typo in `.env` never crashes server startup.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("env var %s=%r is not an int; using default %d", name, raw, default)
        return default


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("env var %s=%r is not a float; using default %s", name, raw, default)
        return default


def env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return raw if raw is not None and raw.strip() != "" else default
