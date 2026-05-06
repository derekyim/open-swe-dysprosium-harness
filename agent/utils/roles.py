"""Load role definitions from the configured build team's roles directory.

Roles are markdown files whose H1 is the human-readable role name (e.g.
`# QA Manager`) and whose filename stem is the slug used by the agent
(e.g. `qa-manager`). Source: `$BUILD_TEAM_DIR/roles/` (override the
roles location specifically with `ROLES_DIR`).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .build_team import get_build_team_dir

logger = logging.getLogger(__name__)

_SKIP_FILES = {"README.md"}


def _roles_dir() -> Path:
    override = os.environ.get("ROLES_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return get_build_team_dir() / "roles"


def _extract_display_name(path: Path) -> str | None:
    """Return the first H1 line in the file, or None if absent."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("# "):
                    return stripped[2:].strip() or None
    except OSError:
        logger.warning("Failed to read role file %s", path)
        return None
    return None


def _scan_roles_dir() -> dict[str, str]:
    """Scan the roles directory and build a `{slug: display_name}` map.

    Synchronous filesystem calls — must be invoked outside any running
    asyncio event loop. We call this once at module import (below) so
    the I/O happens during server startup, not on a request.
    """
    roles_dir = _roles_dir()
    if not roles_dir.is_dir():
        logger.info("Roles directory not found at %s; role_status disabled", roles_dir)
        return {}

    roles: dict[str, str] = {}
    try:
        for path in sorted(roles_dir.glob("*.md")):
            if path.name in _SKIP_FILES:
                continue
            display = _extract_display_name(path) or path.stem.replace("-", " ").title()
            roles[path.stem] = display
    except OSError:
        logger.exception("Failed to scan roles directory at %s", roles_dir)
        return {}
    return roles


# Computed once at module import to keep filesystem I/O off the event loop.
# `langgraph dev`'s blockbuster guard rejects sync filesystem calls (notably
# `os.scandir` via `Path.glob`) when invoked from within an async request.
_ROLES: dict[str, str] = _scan_roles_dir()


def load_roles() -> dict[str, str]:
    """Return the `{slug: display_name}` mapping of available roles.

    Empty dict if the roles directory does not exist; this lets the
    agent run without role announcements when the kit is not in use.
    """
    return _ROLES


def get_role_display_name(slug: str) -> str | None:
    """Resolve a role slug to its display name, or None if unknown."""
    return _ROLES.get(slug)


def format_roles_for_prompt() -> str:
    """Render the role list as bullet lines for inclusion in a prompt."""
    if not _ROLES:
        return ""
    lines = [f"- `{slug}` — {display}" for slug, display in sorted(_ROLES.items())]
    return "\n".join(lines)
