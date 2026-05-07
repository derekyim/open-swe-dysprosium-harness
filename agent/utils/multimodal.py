"""Utilities for building multimodal content blocks."""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from langchain_core.messages.content import create_image_block

from .github_app import get_github_app_installation_token
from .image import downscale_image_bytes

logger = logging.getLogger(__name__)

IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+)\)")
IMAGE_URL_RE = re.compile(
    r"(https?://[^\s)]+\.(?:png|jpe?g|gif|webp|bmp|tiff)(?:\?[^\s)]+)?)",
    re.IGNORECASE,
)
# github.com/<owner>/<repo>/blob/<branch>/<path> → raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>
# `blob/` URLs are HTML viewer pages; only `raw/` (or raw.githubusercontent.com)
# returns the actual file bytes. Same trick GitHub's "Raw" button does.
GITHUB_BLOB_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/blob/(.+)$",
    re.IGNORECASE,
)


def extract_image_urls(text: str) -> list[str]:
    """Extract image URLs from markdown image syntax and direct image links."""
    if not text:
        return []

    urls: list[str] = []
    urls.extend(IMAGE_MARKDOWN_RE.findall(text))
    urls.extend(IMAGE_URL_RE.findall(text))

    deduped = dedupe_urls(urls)
    if deduped:
        logger.debug("Extracted %d image URL(s)", len(deduped))
    return deduped


def _rewrite_github_blob(url: str) -> str:
    """Rewrite `github.com/<o>/<r>/blob/<...>` to raw.githubusercontent.com."""
    m = GITHUB_BLOB_RE.match(url)
    if not m:
        return url
    owner, repo, rest = m.group(1), m.group(2), m.group(3)
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{rest}"


async def fetch_image_block(
    image_url: str,
    client: httpx.AsyncClient,
) -> dict[str, Any] | None:
    """Fetch image bytes and build an image content block."""
    try:
        # Rewrite GitHub `blob/` URLs (HTML viewer) to raw URLs (file bytes).
        original_url = image_url
        image_url = _rewrite_github_blob(image_url)
        if image_url != original_url:
            logger.debug("Rewrote GitHub blob URL: %s -> %s", original_url, image_url)

        logger.debug("Fetching image from %s", image_url)
        headers = None
        host = (urlparse(image_url).hostname or "").lower()
        if host == "uploads.linear.app" or host.endswith(".uploads.linear.app"):
            linear_api_key = os.environ.get("LINEAR_API_KEY", "")
            if linear_api_key:
                headers = {"Authorization": linear_api_key}
            else:
                logger.warning(
                    "LINEAR_API_KEY not set; cannot authenticate image fetch for %s",
                    image_url,
                )
        elif host == "files.slack.com" or host.endswith(".files.slack.com"):
            slack_bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
            if slack_bot_token:
                headers = {"Authorization": f"Bearer {slack_bot_token}"}
            else:
                logger.warning(
                    "SLACK_BOT_TOKEN not set; cannot authenticate image fetch for %s",
                    image_url,
                )
        elif host == "raw.githubusercontent.com" or host == "github.com":
            # Private repos: raw.githubusercontent.com requires a token.
            # The harness's GitHub App installation token works.
            gh_token = await get_github_app_installation_token()
            if gh_token:
                headers = {"Authorization": f"Bearer {gh_token}"}
            else:
                logger.warning(
                    "No GitHub App installation token available; "
                    "fetch may 404 for private repos: %s",
                    image_url,
                )
        response = await client.get(image_url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        if not content_type:
            guessed, _ = mimetypes.guess_type(image_url)
            if not guessed:
                logger.warning(
                    "Could not determine content type for %s; skipping image",
                    image_url,
                )
                return None
            content_type = guessed

        supported_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
        if content_type not in supported_types:
            logger.warning(
                "Unsupported content type '%s' for %s; skipping image",
                content_type,
                image_url,
            )
            return None

        # Downscale to fit Anthropic's 2000px many-image limit. No-op for
        # small images. Resize emits PNG so the mime_type may change.
        raw_bytes = response.content
        model_bytes, model_mime, original_dims, new_dims = downscale_image_bytes(
            raw_bytes, content_type
        )
        if new_dims and original_dims:
            logger.info(
                "Downscaled image from %s: %dx%d -> %dx%d (%s -> %s, %d -> %d bytes)",
                image_url,
                original_dims[0],
                original_dims[1],
                new_dims[0],
                new_dims[1],
                content_type,
                model_mime,
                len(raw_bytes),
                len(model_bytes),
            )

        encoded = base64.b64encode(model_bytes).decode("ascii")
        logger.info(
            "Fetched image %s (%s, %d bytes)",
            image_url,
            model_mime,
            len(model_bytes),
        )
        return create_image_block(base64=encoded, mime_type=model_mime)
    except Exception:
        logger.exception("Failed to fetch image from %s", image_url)
        return None


def dedupe_urls(urls: list[str]) -> list[str]:
    return list(dict.fromkeys(urls))
