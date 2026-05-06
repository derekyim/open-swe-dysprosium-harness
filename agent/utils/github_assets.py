"""Upload binary assets (screenshots, etc.) to a GitHub repo via the Contents API.

Uses a dedicated `_screenshots` branch per repo so the assets stay
visible in GitHub but don't pollute the working PR diff. The branch is
auto-created from the default branch's HEAD if it doesn't exist.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API = "https://api.github.com"
SCREENSHOT_BRANCH = "_screenshots"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _branch_exists(
    client: httpx.AsyncClient, owner: str, repo: str, branch: str, token: str
) -> bool:
    response = await client.get(
        f"{API}/repos/{owner}/{repo}/git/ref/heads/{branch}", headers=_headers(token)
    )
    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return False


async def _default_branch_sha(client: httpx.AsyncClient, owner: str, repo: str, token: str) -> str:
    repo_info = await client.get(f"{API}/repos/{owner}/{repo}", headers=_headers(token))
    repo_info.raise_for_status()
    default_branch = repo_info.json()["default_branch"]
    ref = await client.get(
        f"{API}/repos/{owner}/{repo}/git/ref/heads/{default_branch}",
        headers=_headers(token),
    )
    ref.raise_for_status()
    return ref.json()["object"]["sha"]


async def _create_branch(
    client: httpx.AsyncClient, owner: str, repo: str, branch: str, sha: str, token: str
) -> None:
    response = await client.post(
        f"{API}/repos/{owner}/{repo}/git/refs",
        headers=_headers(token),
        json={"ref": f"refs/heads/{branch}", "sha": sha},
    )
    response.raise_for_status()


async def _ensure_screenshot_branch(
    client: httpx.AsyncClient, owner: str, repo: str, token: str
) -> None:
    if await _branch_exists(client, owner, repo, SCREENSHOT_BRANCH, token):
        return
    sha = await _default_branch_sha(client, owner, repo, token)
    logger.info("Creating %s branch in %s/%s from %s", SCREENSHOT_BRANCH, owner, repo, sha[:8])
    await _create_branch(client, owner, repo, SCREENSHOT_BRANCH, sha, token)


async def _existing_file_sha(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    path: str,
    branch: str,
    token: str,
) -> str | None:
    """Return the existing file's blob SHA if present (needed to overwrite)."""
    response = await client.get(
        f"{API}/repos/{owner}/{repo}/contents/{path}",
        headers=_headers(token),
        params={"ref": branch},
    )
    if response.status_code == 200:
        body = response.json()
        return body.get("sha") if isinstance(body, dict) else None
    return None


async def upload_image_to_screenshot_branch(
    repo_owner: str,
    repo_name: str,
    repo_path: str,
    local_path: Path,
    commit_message: str,
    token: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Commit `local_path` to the repo's screenshots branch under `repo_path`.

    Returns a dict with `success`, `raw_url`, `path` (in-repo), and
    `branch`. On failure, includes `error` and the HTTP status if known.
    """
    if not local_path.is_file():
        return {"success": False, "error": f"file not found: {local_path}"}
    data = local_path.read_bytes()
    if not data:
        return {"success": False, "error": f"file is empty: {local_path}"}
    encoded = base64.b64encode(data).decode("ascii")

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        try:
            await _ensure_screenshot_branch(client, repo_owner, repo_name, token)

            existing_sha = await _existing_file_sha(
                client, repo_owner, repo_name, repo_path, SCREENSHOT_BRANCH, token
            )
            put_body: dict[str, Any] = {
                "message": commit_message,
                "content": encoded,
                "branch": SCREENSHOT_BRANCH,
            }
            if existing_sha:
                put_body["sha"] = existing_sha

            response = await client.put(
                f"{API}/repos/{repo_owner}/{repo_name}/contents/{repo_path}",
                headers=_headers(token),
                json=put_body,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.exception("GitHub Contents API upload failed")
            return {
                "success": False,
                "status": exc.response.status_code,
                "error": f"{exc.response.status_code}: {exc.response.text[:500]}",
            }
        except httpx.HTTPError as exc:
            logger.exception("GitHub Contents API request failed")
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    raw_url = (
        f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/"
        f"{SCREENSHOT_BRANCH}/{repo_path}"
    )
    blob_url = f"https://github.com/{repo_owner}/{repo_name}/blob/{SCREENSHOT_BRANCH}/{repo_path}"
    return {
        "success": True,
        "raw_url": raw_url,
        "blob_url": blob_url,
        "path": repo_path,
        "branch": SCREENSHOT_BRANCH,
        "bytes": len(data),
    }
