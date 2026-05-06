"""Locate the build-team checkout configured for this harness deployment.

A build team is a sibling repo (or absolute path) containing the
project-specific roles, templates, playbooks, and per-deployment
`default_prompt.md`. Per-project content lives there, the harness
itself stays generic.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DIR_NAME = "build-team"


@lru_cache(maxsize=1)
def get_build_team_dir() -> Path:
    """Return the resolved path to the build team checkout.

    Reads `BUILD_TEAM_DIR` from the environment. If unset, falls back
    to `<harness_root>/build-team`. Relative paths resolve against the
    harness repo root, not the current working directory, so the path
    is stable regardless of where the process was launched from.
    """
    raw = os.environ.get("BUILD_TEAM_DIR", "").strip()
    if not raw:
        return _REPO_ROOT / _DEFAULT_DIR_NAME
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (_REPO_ROOT / path).resolve()
    return path


def get_build_team_name() -> str:
    return os.environ.get("BUILD_TEAM_NAME", "").strip() or "Build Team"


def get_build_team_repo_url() -> str | None:
    raw = os.environ.get("BUILD_TEAM_REPO_URL", "").strip()
    return raw or None
