"""Append a durable lesson to the build team's memory directory."""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any

from ..utils.memory import memory_dir

logger = logging.getLogger(__name__)

_CATEGORY_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
_CATEGORY_HINT = (
    "lowercase letters, digits, and hyphens; 2-41 chars; must start with a letter "
    "(e.g. `architecture-decisions`, `known-failures`, `deploy-gotchas`)"
)


def _new_entry(title: str, body: str, today: str) -> str:
    title = title.strip().rstrip(".")
    body = body.strip()
    return f"\n\n---\n\n### {today} — {title}\n\n{body}\n\n_Last verified: {today}_\n"


def _file_header(category: str) -> str:
    display = category.replace("-", " ").replace("_", " ").title()
    return (
        f"# {display}\n\n"
        f"Durable lessons recorded by the build team. Each entry: one "
        f"non-obvious thing a future run would otherwise re-learn. Keep "
        f"entries short and constraint-shaped, not task-shaped.\n"
    )


def record_lesson(category: str, title: str, body: str) -> dict[str, Any]:
    """Append a lesson learned to `$BUILD_TEAM_DIR/memory/<category>.md`.

    Use this **sparingly** — only when you have just discovered
    something *non-obvious* that a future run would otherwise re-learn
    the hard way. Good lessons name a constraint, a gotcha, or a
    decision-with-rationale. Bad lessons restate what's already in the
    code or describe one-off task details.

    A good lesson reads: "When changing X, the Y backend rejects Z
    because <reason>. Use <approach> instead." A bad one reads:
    "Fixed bug in issue #123 by editing foo.py."

    The new entry is appended to the category file with today's date.
    The build team's git history captures who recorded what, when —
    so commit the change after a lesson is recorded for it to persist.

    Args:
        category: Filename slug for the bucket the lesson belongs to.
            Lowercase letters, digits, hyphens (e.g.
            `architecture-decisions`, `known-failures`, `deploy-gotchas`).
            Reuse existing categories where possible — a quick `ls
            $BUILD_TEAM_DIR/memory/` shows what's there.
        title: One-line title (≤ 80 chars). What's the lesson, in
            five-to-ten words?
        body: One-to-three short paragraphs. Lead with the constraint
            or fact. Then a brief *why*. Then "How to apply" if it's
            non-obvious.

    Returns:
        Dict with `success` (bool), `path` (file written), `category`,
        `entry_preview` (first ~200 chars of the appended block), and
        `error` on failure.
    """
    if not _CATEGORY_RE.match(category):
        return {
            "success": False,
            "error": f"invalid category {category!r}; must match: {_CATEGORY_HINT}",
        }
    if not title.strip():
        return {"success": False, "error": "title cannot be empty"}
    if not body.strip():
        return {"success": False, "error": "body cannot be empty"}

    directory = memory_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "success": False,
            "error": f"could not create memory directory {directory}: {exc}",
        }

    path = directory / f"{category}.md"
    today = datetime.date.today().isoformat()
    entry = _new_entry(title, body, today)

    try:
        is_new = not path.exists()
        with path.open("a", encoding="utf-8") as fh:
            if is_new:
                fh.write(_file_header(category))
            fh.write(entry)
    except OSError as exc:
        logger.exception("failed to write lesson")
        return {
            "success": False,
            "error": f"could not write to {path}: {exc}",
        }

    preview = entry.strip()[:300]
    return {
        "success": True,
        "path": str(path),
        "category": category,
        "is_new_file": is_new,
        "entry_preview": preview,
        "next_steps": (
            "Commit this change in the build team repo so the lesson "
            "persists for future runs. Until committed, the lesson lives "
            "only in your local checkout."
        ),
    }
