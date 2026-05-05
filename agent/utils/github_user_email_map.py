"""Mapping of GitHub usernames to LangSmith email addresses.

Loaded from the `GITHUB_USER_EMAIL_MAP_JSON` environment variable as a
single-line JSON object, e.g.

    GITHUB_USER_EMAIL_MAP_JSON='{"alice": "alice@example.com"}'

If the env var is unset or malformed, the map is empty — the harness
still runs but no GitHub login resolves to an email.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_ENV_VAR = "GITHUB_USER_EMAIL_MAP_JSON"


def _load_map() -> dict[str, str]:
    raw = os.environ.get(_ENV_VAR, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("%s is set but is not valid JSON; ignoring", _ENV_VAR)
        return {}
    if not isinstance(parsed, dict):
        logger.warning("%s must be a JSON object; got %s", _ENV_VAR, type(parsed).__name__)
        return {}
    result: dict[str, str] = {}
    for k, v in parsed.items():
        if isinstance(k, str) and isinstance(v, str):
            result[k] = v
        else:
            logger.warning("%s entry %r → %r is not a string→string pair; skipping", _ENV_VAR, k, v)
    return result


GITHUB_USER_EMAIL_MAP: dict[str, str] = _load_map()
