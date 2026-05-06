"""Load the list of product repositories the agent can operate on.

Resolution order:

1. `PROJECT_REPOS_JSON` env var (a JSON array) — for one-off overrides.
2. `$BUILD_TEAM_DIR/repos.json` — the canonical source. Ships with the
   build team so the team agrees on which repos compose the product.
3. No list — the agent falls back to single-repo behavior using
   `DEFAULT_REPO_OWNER` / `DEFAULT_REPO_NAME`.

Each entry is a dict:

    {
      "slug": "frontend",                           # required, unique
      "repo": "derekyim/agent-quality-helper",      # required, "owner/name"
      "local_checkout": "../agent-quality-helper",  # optional
      "purpose": "Next.js companion app + sidecar"  # optional
    }
"""

from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from typing import Any

from .build_team import get_build_team_dir

logger = logging.getLogger(__name__)

_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


def _validate(entry: Any, idx: int) -> dict[str, Any] | None:
    """Validate one entry; log and drop invalid ones."""
    if not isinstance(entry, dict):
        logger.warning("project repo entry #%d is not an object; skipping", idx)
        return None

    slug = entry.get("slug")
    repo = entry.get("repo")
    if not isinstance(slug, str) or not slug.strip():
        logger.warning("project repo entry #%d missing 'slug'; skipping", idx)
        return None
    if not isinstance(repo, str) or not _REPO_RE.match(repo):
        logger.warning(
            "project repo entry #%d has invalid 'repo' %r (expected 'owner/name'); skipping",
            idx,
            repo,
        )
        return None

    cleaned: dict[str, Any] = {"slug": slug.strip(), "repo": repo.strip()}
    for key in ("local_checkout", "purpose"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            cleaned[key] = value.strip()
    return cleaned


def _parse_list(raw: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        logger.warning("%s: expected a JSON array, got %s", source, type(raw).__name__)
        return []
    out: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for i, entry in enumerate(raw):
        cleaned = _validate(entry, i)
        if cleaned is None:
            continue
        if cleaned["slug"] in seen_slugs:
            logger.warning(
                "duplicate slug %r in %s; keeping first occurrence", cleaned["slug"], source
            )
            continue
        seen_slugs.add(cleaned["slug"])
        out.append(cleaned)
    return out


def _load_from_env() -> list[dict[str, Any]] | None:
    raw = os.environ.get("PROJECT_REPOS_JSON", "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("PROJECT_REPOS_JSON is set but is not valid JSON; ignoring")
        return None
    return _parse_list(parsed, "PROJECT_REPOS_JSON")


def _load_from_file() -> list[dict[str, Any]]:
    path = get_build_team_dir() / "repos.json"
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            parsed = json.load(fh)
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to load %s; ignoring", path)
        return []
    return _parse_list(parsed, str(path))


@lru_cache(maxsize=1)
def load_project_repos() -> list[dict[str, Any]]:
    """Return the validated list of project repos, or [] if none configured."""
    env_list = _load_from_env()
    if env_list is not None:
        logger.info("Loaded %d project repo(s) from PROJECT_REPOS_JSON", len(env_list))
        return env_list
    file_list = _load_from_file()
    if file_list:
        logger.info("Loaded %d project repo(s) from $BUILD_TEAM_DIR/repos.json", len(file_list))
    return file_list


def format_repos_for_prompt() -> str:
    """Render the repo list as a markdown bullet block for the system prompt.

    Empty string when no repos are configured — the section is then
    omitted entirely.
    """
    repos = load_project_repos()
    if not repos:
        return ""
    lines = []
    for entry in repos:
        line = f"- `{entry['slug']}` — `{entry['repo']}`"
        if entry.get("purpose"):
            line += f" — {entry['purpose']}"
        if entry.get("local_checkout"):
            line += f" (local checkout: `{entry['local_checkout']}`)"
        lines.append(line)
    return "\n".join(lines)
