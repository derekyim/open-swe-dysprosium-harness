"""Load durable lessons from the build team's memory directory.

The build team is expected to keep a `memory/` directory of markdown
files — one per category (e.g. `architecture-decisions.md`,
`known-failures.md`). Each file is appended to as the agent records
new lessons via the `record_lesson` tool.

These are eager-loaded at module import (synchronous filesystem I/O
must not happen on the request path — `langgraph dev`'s blockbuster
guard rejects it). Lessons recorded by the running agent become
visible on the next process restart.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .build_team import get_build_team_dir

logger = logging.getLogger(__name__)

_SKIP_FILES = {"README.md"}
_MEMORY_SUBDIR = "memory"

# Per-file cap (characters). When exceeded, the file's *tail* is kept
# — newest entries should be at the bottom because `record_lesson`
# appends. A "truncated" notice is prepended so the agent knows.
_MAX_CHARS_PER_FILE = 8_000


def memory_dir() -> Path:
    """Return the resolved path to the memory directory."""
    return get_build_team_dir() / _MEMORY_SUBDIR


def _read_capped(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Failed to read memory file %s", path)
        return ""
    text = text.strip()
    if len(text) <= _MAX_CHARS_PER_FILE:
        return text
    tail = text[-_MAX_CHARS_PER_FILE:]
    return f"_(earlier entries truncated to keep the prompt small)_\n\n{tail}"


def _scan() -> dict[str, str]:
    """Read every memory file, skipping README and dirs.

    Returns a dict: `{category_slug: content}` keyed by filename stem,
    sorted alphabetically. Empty if the dir doesn't exist.
    """
    directory = memory_dir()
    if not directory.is_dir():
        logger.info("Memory directory not found at %s; durable lessons disabled", directory)
        return {}

    out: dict[str, str] = {}
    try:
        for path in sorted(directory.glob("*.md")):
            if path.name in _SKIP_FILES:
                continue
            content = _read_capped(path)
            if content:
                out[path.stem] = content
    except OSError:
        logger.exception("Failed to scan memory directory at %s", directory)
        return {}
    return out


# Eager-loaded at module import so we never touch the filesystem from
# inside an asyncio handler.
_MEMORY: dict[str, str] = _scan()


def load_memory() -> dict[str, str]:
    """Return the cached `{category: content}` map of durable lessons."""
    return _MEMORY


def format_memory_for_prompt() -> str:
    """Render the memory content as a markdown block for the system prompt.

    Empty string when no memory is configured — the section is then
    omitted entirely.
    """
    if not _MEMORY:
        return ""
    parts: list[str] = []
    for category, content in _MEMORY.items():
        display = category.replace("-", " ").replace("_", " ").title()
        parts.append(f"#### {display}  (`memory/{category}.md`)\n\n{content}")
    return "\n\n".join(parts)
