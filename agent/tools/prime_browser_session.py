"""Run a browser login (or any priming) flow once and persist the session.

The tool drives a headless Chromium through a caller-supplied sequence of
steps (`click`, `fill`, `wait_for_selector`, `wait_for_url`, `goto`) and
persists the full browser profile (cookies + localStorage + **IndexedDB**)
to a `user_data_dir` on disk. Subsequent `screenshot` calls passing the
same `browser_profile_dir` reuse the session, so N screenshots cost 1
login.

Why a full profile dir and not just `storage_state`? Firebase Auth (and
several other modern SDKs) persist the session to IndexedDB. Playwright's
`storage_state` only captures cookies + localStorage, so it loses Firebase
auth. `launch_persistent_context(user_data_dir=...)` captures everything.

Step `value` fields support `{ENV_VAR}` placeholders that get substituted
from `os.environ` inside the tool. The agent never sees the secret in its
message stream — it passes the placeholder string instead.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_BROWSER_PROFILE_DIR = "/tmp/dysprosium_browser_profile"
_ALLOWED_ACTIONS = {"goto", "click", "fill", "wait_for_selector", "wait_for_url"}
_PLACEHOLDER_RE = re.compile(r"\{([A-Z_][A-Z0-9_]*)\}")


def _substitute_env(value: str) -> str:
    """Replace `{ENV_VAR}` placeholders with values from os.environ.

    Raises KeyError listing missing vars instead of silently leaving the
    placeholder in place — empty creds would cause a confusing 401 later.
    """
    missing: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        val = os.environ.get(name)
        if val is None:
            missing.append(name)
            return match.group(0)
        return val

    out = _PLACEHOLDER_RE.sub(repl, value)
    if missing:
        raise KeyError(f"Missing env vars referenced in step value: {missing}")
    return out


def _redact(value: str) -> str:
    """Best-effort log redaction — never log substituted values verbatim."""
    return _PLACEHOLDER_RE.sub(r"{\1}", value) if _PLACEHOLDER_RE.search(value) else "<value>"


def _prime_browser_session_sync(
    login_url: str,
    steps: list[dict[str, str]],
    browser_profile_dir: str,
    success_selector: str | None,
    success_url_contains: str | None,
    viewport_width: int,
    viewport_height: int,
    timeout_seconds: int,
    ignore_https_errors: bool,
    reset_profile: bool,
) -> dict[str, Any]:
    """Sync inner — runs on a worker thread via `asyncio.to_thread`.

    Playwright's sync API and the surrounding filesystem operations
    (`shutil.rmtree`, `Path.mkdir`) are all blocking; LangGraph's
    blockbuster instrumentation refuses them on the event loop, so the
    public `prime_browser_session` is async and offloads here.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "success": False,
            "error": (
                "Playwright is not installed. Run `make playwright-install` for local "
                "mode, or rebuild the sandbox image."
            ),
        }

    profile_dir = Path(browser_profile_dir)
    if reset_profile and profile_dir.exists():
        shutil.rmtree(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)

    timeout_ms = timeout_seconds * 1000
    log: list[str] = []
    final_url: str | None = None

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=True,
            viewport={"width": viewport_width, "height": viewport_height},
            ignore_https_errors=ignore_https_errors,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.on("pageerror", lambda err: log.append(f"pageerror: {err}"))

            log.append(f"goto {login_url}")
            page.goto(login_url, wait_until="domcontentloaded", timeout=timeout_ms)

            for idx, step in enumerate(steps):
                action = step.get("action")
                if action not in _ALLOWED_ACTIONS:
                    return {
                        "success": False,
                        "error": f"unknown action {action!r}; allowed: {sorted(_ALLOWED_ACTIONS)}",
                        "step_index": idx,
                        "step": step,
                        "final_url": page.url,
                        "log": log,
                    }
                step_timeout = int(step.get("timeout_seconds", timeout_seconds)) * 1000
                selector = step.get("selector", "")
                try:
                    if action == "goto":
                        log.append(f"[{idx}] goto {selector}")
                        page.goto(selector, wait_until="domcontentloaded", timeout=step_timeout)
                    elif action == "click":
                        log.append(f"[{idx}] click {selector}")
                        page.locator(selector).first.click(timeout=step_timeout)
                    elif action == "fill":
                        raw = step.get("value", "")
                        value = _substitute_env(raw)
                        log.append(f"[{idx}] fill {selector} = {_redact(raw)}")
                        page.locator(selector).first.fill(value, timeout=step_timeout)
                    elif action == "wait_for_selector":
                        log.append(f"[{idx}] wait_for_selector {selector}")
                        page.wait_for_selector(selector, timeout=step_timeout)
                    elif action == "wait_for_url":
                        log.append(f"[{idx}] wait_for_url contains {selector}")
                        needle = selector
                        page.wait_for_url(
                            lambda url, needle=needle: needle in url,
                            timeout=step_timeout,
                        )
                except KeyError as exc:
                    return {
                        "success": False,
                        "error": str(exc),
                        "step_index": idx,
                        "step": {**step, "value": _redact(step.get("value", ""))},
                        "final_url": page.url,
                        "log": log,
                    }
                except Exception as exc:  # noqa: BLE001 — Playwright errors are diverse
                    return {
                        "success": False,
                        "error": f"{type(exc).__name__}: {exc}",
                        "step_index": idx,
                        "step": {**step, "value": _redact(step.get("value", ""))},
                        "final_url": page.url,
                        "log": log,
                    }

            if success_selector:
                log.append(f"verify success_selector {success_selector}")
                try:
                    page.wait_for_selector(success_selector, timeout=timeout_ms)
                except Exception as exc:  # noqa: BLE001
                    return {
                        "success": False,
                        "error": f"success_selector not found: {type(exc).__name__}: {exc}",
                        "final_url": page.url,
                        "log": log,
                    }

            if success_url_contains and success_url_contains not in page.url:
                return {
                    "success": False,
                    "error": (
                        f"final URL {page.url!r} does not contain {success_url_contains!r}"
                    ),
                    "final_url": page.url,
                    "log": log,
                }

            final_url = page.url
            log.append(f"persisted profile to {profile_dir}")

        finally:
            # context.close() flushes IndexedDB, cookies, localStorage to disk.
            context.close()

    return {
        "success": True,
        "browser_profile_dir": str(profile_dir),
        "final_url": final_url,
        "steps_completed": len(steps),
        "log": log,
    }


async def prime_browser_session(
    login_url: str,
    steps: list[dict[str, str]],
    browser_profile_dir: str = DEFAULT_BROWSER_PROFILE_DIR,
    success_selector: str | None = None,
    success_url_contains: str | None = None,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    timeout_seconds: int = 30,
    ignore_https_errors: bool = True,
    reset_profile: bool = True,
) -> dict[str, Any]:
    """Run a browser flow (typically login), persist the full profile.

    Args:
        login_url: First URL to load. Typical: the app's root or login route.
        steps: Ordered list of step dicts. Each step has:
            - `action`: one of `goto`, `click`, `fill`,
              `wait_for_selector`, `wait_for_url`.
            - `selector` (for `click`, `fill`, `wait_for_selector`): a
              CSS selector. For `wait_for_url`, the URL substring to
              match. For `goto`, the destination URL.
            - `value` (only for `fill`): the text to type. Supports
              `{ENV_VAR}` placeholders which are substituted from
              `os.environ` inside the tool — keep secrets out of the
              LLM message stream by passing `"{TEST_USER_PASSWORD}"`
              rather than the literal password.
            - `timeout_seconds` (optional): per-step override of the
              default `timeout_seconds`.
        browser_profile_dir: Path to a directory where Playwright will
            persist the full Chromium profile (cookies, localStorage,
            IndexedDB, service workers). Pass this same path to
            `screenshot(browser_profile_dir=...)` to reuse the session.
            Required for SDKs that persist auth to IndexedDB (Firebase,
            etc.) — `storage_state` JSON is not enough.
        success_selector: Optional CSS selector that must be visible
            after the steps run. Strongly recommended — confirms the
            flow actually succeeded before persisting the profile.
        success_url_contains: Optional substring that must appear in the
            final URL after the steps run.
        viewport_width / viewport_height: Browser viewport.
        timeout_seconds: Default per-step timeout. Default 30.
        ignore_https_errors: Tolerate self-signed TLS certs (default True).
        reset_profile: If True (default), wipe `browser_profile_dir`
            before priming so a stale or partially-populated profile
            cannot mask a fresh failure. Set False to layer additional
            steps onto an existing profile.

    Returns:
        On success: `{"success": True, "browser_profile_dir": str,
            "final_url": str, "steps_completed": int, "log": [str, ...]}`.
        On failure: `{"success": False, "error": str, "step_index": int,
            "step": dict, "final_url": str | None, "log": [str, ...]}`.
    """
    return await asyncio.to_thread(
        _prime_browser_session_sync,
        login_url,
        steps,
        browser_profile_dir,
        success_selector,
        success_url_contains,
        viewport_width,
        viewport_height,
        timeout_seconds,
        ignore_https_errors,
        reset_profile,
    )
