"""Capture a screenshot of a URL with a headless Chromium browser.

Returns a multimodal content list (text summary + image block) so the
model can actually see the rendered UI. Also captures `console` and
`pageerror` events as text in the summary, so JS errors surface without
a separate tool call.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from pathlib import Path
from typing import Any

from langchain_core.messages.content import create_image_block, create_text_block

logger = logging.getLogger(__name__)

SCREENSHOT_DIR = Path("/tmp/dysprosium_screenshots")
_CONSOLE_TAIL = 30
_ERROR_TAIL = 10


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return cleaned[:60] or "screenshot"


def _capture(
    url: str,
    viewport: tuple[int, int],
    wait_for: str | None,
    full_page: bool,
    timeout_ms: int,
) -> tuple[bytes, Path, list[str], list[str]]:
    from playwright.sync_api import sync_playwright

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SCREENSHOT_DIR / f"{int(time.time() * 1000)}_{_slugify(url)}.png"
    console: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
            page = context.new_page()
            page.on("console", lambda msg: console.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_for:
                page.wait_for_selector(wait_for, timeout=timeout_ms)

            png_bytes = page.screenshot(path=str(out_path), full_page=full_page)
        finally:
            browser.close()

    return png_bytes, out_path, console, page_errors


def screenshot(
    url: str,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    wait_for: str | None = None,
    full_page: bool = False,
    timeout_seconds: int = 30,
) -> list[dict[str, Any]] | str:
    """Capture a screenshot of a URL using a headless Chromium browser.

    The returned content includes the rendered image so you can visually
    verify the UI. Console messages and page errors captured during the
    visit are included in the text summary.

    Args:
        url: Full URL to visit (e.g. `http://localhost:3000/dashboard`).
            For local apps, start them first with `start_app`.
        viewport_width: Browser viewport width in pixels (default 1280).
        viewport_height: Browser viewport height in pixels (default 800).
        wait_for: Optional CSS selector to wait for before capturing. Use
            this for SPAs whose content loads after `domcontentloaded`,
            e.g. `wait_for="[data-testid='dashboard']"`.
        full_page: If True, capture the full scrollable page rather than
            just the viewport. Default False.
        timeout_seconds: Per-step timeout for navigation and the
            `wait_for` selector. Default 30.

    Returns:
        On success: a multimodal list with a text summary (URL, save
        path, console messages, page errors) and a PNG image block.
        On failure: a one-line error string.
    """
    try:
        png_bytes, path, console, errors = _capture(
            url,
            (viewport_width, viewport_height),
            wait_for,
            full_page,
            timeout_seconds * 1000,
        )
    except ImportError:
        return (
            "Playwright is not installed. Run `make playwright-install` for local mode, "
            "or rebuild the sandbox image (the Dockerfile pre-installs Chromium)."
        )
    except Exception as exc:  # noqa: BLE001 — Playwright errors are diverse
        logger.exception("screenshot failed for %s", url)
        return f"Screenshot of {url} failed: {type(exc).__name__}: {exc}"

    summary = [f"Screenshot of {url}", f"Saved: {path}", f"Bytes: {len(png_bytes)}"]
    if errors:
        summary.append(f"\nPage errors ({len(errors)}, last {min(len(errors), _ERROR_TAIL)}):")
        summary.extend(errors[-_ERROR_TAIL:])
    if console:
        summary.append(
            f"\nConsole messages ({len(console)}, last {min(len(console), _CONSOLE_TAIL)}):"
        )
        summary.extend(console[-_CONSOLE_TAIL:])

    encoded = base64.b64encode(png_bytes).decode("ascii")
    return [
        create_text_block("\n".join(summary)),
        create_image_block(base64=encoded, mime_type="image/png"),
    ]
