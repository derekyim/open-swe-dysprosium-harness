"""Upload a local image to a hosted location and return a markdown link.

Auto-routes based on the run's source channel. For GitHub-triggered
runs, commits to a `_screenshots` branch in the same repo and returns a
raw.githubusercontent.com URL the agent can embed in a `github_comment`
message. Linear and Slack uploads are not yet implemented.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any

from langgraph.config import get_config

from ..utils.github_app import get_github_app_installation_token
from ..utils.github_assets import upload_image_to_screenshot_branch

logger = logging.getLogger(__name__)

_ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _safe_basename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._-")
    return cleaned or "image"


def _build_repo_path(thread_id: str, local_path: Path) -> str:
    """Construct the in-branch path: `<thread_short>/<ts>_<basename>`."""
    short = (thread_id or "unknown")[:8]
    ts = int(time.time() * 1000)
    return f"{short}/{ts}_{_safe_basename(local_path.name)}"


def upload_image(local_path: str, label: str = "") -> dict[str, Any]:
    """Upload a local image to the source repo's `_screenshots` branch.

    Use this to surface visual evidence in a Linear/GitHub comment — the
    returned `markdown` is a self-contained `![](raw_url)` line you can
    embed in a `github_comment` / `linear_comment` body.

    The image is committed to the repo's `_screenshots` branch (created
    on first use) under `<thread_id_short>/<timestamp>_<basename>`. The
    branch is shared across runs but per-thread folders keep the work
    isolated.

    Args:
        local_path: Path to a `.png` / `.jpg` / `.jpeg` / `.gif` /
            `.webp` file on disk. Relative paths resolve against the
            current working directory.
        label: Optional caption used as the markdown alt text and the
            commit message tail. Helpful for diff readability.

    Returns:
        Dict. On success: `success=True`, `markdown` (ready to embed),
        `raw_url`, `path` (in-repo), `branch`, `bytes`. On failure:
        `success=False`, `error`, and `channel` indicating which path
        was attempted.
    """
    path = Path(local_path).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    if not path.is_file():
        return {"success": False, "error": f"file not found: {local_path}", "channel": "none"}
    if path.suffix.lower() not in _ALLOWED_EXTS:
        return {
            "success": False,
            "error": f"unsupported extension {path.suffix!r}; allowed: {sorted(_ALLOWED_EXTS)}",
            "channel": "none",
        }

    config = get_config()
    configurable = config.get("configurable", {})
    source = configurable.get("source", "")

    if source == "github":
        return _upload_to_github(configurable, path, label)
    if source in ("linear", "slack"):
        return {
            "success": False,
            "channel": source,
            "error": (
                f"upload_image is not yet implemented for source={source!r}. "
                "For now, run this on a GitHub-triggered task or have the agent "
                "commit the image into the working PR branch."
            ),
        }
    return {
        "success": False,
        "channel": "none",
        "error": f"unknown source {source!r}; expected 'github' / 'linear' / 'slack'",
    }


def _upload_to_github(configurable: dict[str, Any], path: Path, label: str) -> dict[str, Any]:
    repo_config = configurable.get("repo") or {}
    owner = repo_config.get("owner")
    name = repo_config.get("name")
    if not owner or not name:
        return {
            "success": False,
            "channel": "github",
            "error": "missing repo.owner / repo.name in configurable",
        }

    thread_id = configurable.get("thread_id") or ""
    repo_path = _build_repo_path(thread_id, path)

    label_for_msg = label.strip() or path.name
    commit_message = f"screenshot: {label_for_msg[:100]}"

    try:
        token = asyncio.run(get_github_app_installation_token())
    except Exception as exc:  # noqa: BLE001
        logger.exception("failed to get GitHub App installation token")
        return {
            "success": False,
            "channel": "github",
            "error": f"could not get installation token: {type(exc).__name__}: {exc}",
        }
    if not token:
        return {
            "success": False,
            "channel": "github",
            "error": "GitHub App installation token unavailable",
        }

    result = asyncio.run(
        upload_image_to_screenshot_branch(
            repo_owner=owner,
            repo_name=name,
            repo_path=repo_path,
            local_path=path,
            commit_message=commit_message,
            token=token,
        )
    )

    if not result.get("success"):
        return {**result, "channel": "github"}

    alt = label.strip() or path.name
    # Clickable link to GitHub's blob viewer — works for both public and
    # private repos when the reader is logged in. Inline `![](raw_url)`
    # embeds do not render for private repos because Camo cannot
    # authenticate to raw.githubusercontent.com; the blob link sidesteps
    # that entirely. `raw_url` is still returned in case the agent wants
    # it for other purposes.
    markdown = f"[{alt}]({result['blob_url']})"
    return {
        **result,
        "channel": "github",
        "markdown": markdown,
    }
