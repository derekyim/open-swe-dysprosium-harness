"""List the configured project repositories for the current deployment."""

from __future__ import annotations

from typing import Any

from ..utils.project_repos import load_project_repos


def list_project_repos() -> dict[str, Any]:
    """Return the structured list of repositories that compose this product.

    The list is loaded from `$BUILD_TEAM_DIR/repos.json` (or the
    `PROJECT_REPOS_JSON` env var override). Each entry has:

    - `slug` — short tag (e.g. `frontend`, `api`, `docs`)
    - `repo` — `owner/name`
    - `local_checkout` — local filesystem path if cloned alongside the
      harness; absent when the agent should clone fresh
    - `purpose` — one-sentence description of what lives in that repo

    Use this when a task spans multiple repos, when you need to decide
    which repo a task belongs to, or when you want to enumerate
    project repos programmatically.

    Returns:
        Dict with `repos` (list) and `count` (int). When no repos are
        configured, returns `{"repos": [], "count": 0}` and the agent
        should fall back to `DEFAULT_REPO_OWNER` / `DEFAULT_REPO_NAME`.
    """
    repos = load_project_repos()
    return {"repos": repos, "count": len(repos)}
