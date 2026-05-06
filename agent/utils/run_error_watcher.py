"""Background task that posts run-level errors back to the source channel.

When an agent run dies before it can speak for itself (e.g. Anthropic
429/529, BlockingError before the first model call, server cancellation,
etc.), the GitHub/Linear/Slack thread otherwise just shows a 👀 with no
follow-up. The watcher polls the local LangGraph API for newly-errored
threads and posts a short "run failed" comment to whichever channel
triggered them, with a one-line hint about what to do next.

Tracking is in-memory only — restarts forget what's been notified, but
that's fine: the runtime guard against duplicate posts is the same
process that's been running the watcher. Errors that predate startup
are not re-announced.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

import httpx

from .env_config import env_int, env_str
from .source_channel import post_to_source

logger = logging.getLogger(__name__)


_ERROR_HINTS: dict[str, str] = {
    "OverloadedError": (
        "The model API was at capacity (HTTP 529). The agent did not retry "
        "on its own — re-mention me to try again. These typically clear in "
        "30–120 seconds."
    ),
    "RateLimitError": (
        "Hit the model provider's rate limit. Wait a minute and re-mention me to retry."
    ),
    "AuthenticationError": (
        "The model provider rejected the API key. Check `.env` "
        "(`ANTHROPIC_API_KEY`, etc.) and restart `langgraph dev` — this "
        "won't fix itself."
    ),
    "BlockingError": (
        "A sync I/O call leaked into an async path (`langgraph dev` guards "
        "against this). This is a harness code bug, not transient — fix "
        "and restart, then re-mention me."
    ),
    "TimeoutError": (
        "A long operation timed out. Re-mention me to retry. If this "
        "persists on the same task, check the LangSmith trace for the "
        "stuck step."
    ),
    "CancelledError": (
        "The run was cancelled — usually when `langgraph dev` auto-reloaded "
        "on a file change mid-call. Re-mention me to retry; consider "
        "`make dev-stable` (which uses `--no-reload`) for long tasks."
    ),
}

_GENERIC_HINT = (
    "The run terminated unexpectedly. Re-mention me to try again. If it "
    "keeps failing the same way, check the harness logs or the LangSmith "
    "trace for the underlying cause."
)


def _format_error_message(error_type: str, raw_message: str) -> str:
    hint = _ERROR_HINTS.get(error_type, _GENERIC_HINT)
    detail = raw_message.strip()
    if len(detail) > 300:
        detail = detail[:297].rstrip() + "…"
    body = f"**❌ Agent run failed.**\n\n_Error type:_ `{error_type}`\n\n{hint}"
    if detail:
        body += f"\n\n_Detail:_ {detail}"
    return body


def _format_error_message_slack(error_type: str, raw_message: str) -> str:
    hint = _ERROR_HINTS.get(error_type, _GENERIC_HINT)
    detail = raw_message.strip()
    if len(detail) > 300:
        detail = detail[:297].rstrip() + "…"
    body = f"*❌ Agent run failed.*\n\n_Error type:_ `{error_type}`\n\n{hint}"
    if detail:
        body += f"\n\n_Detail:_ {detail}"
    return body


def _decode_error_blob(blob: str) -> tuple[str, str] | None:
    """Decode the LangGraph error envelope: base64(JSON({error, message})).

    Returns `(error_type, message)` or None if the blob is malformed.
    """
    try:
        parsed = json.loads(base64.b64decode(blob).decode())
    except (ValueError, UnicodeDecodeError):
        try:
            parsed = json.loads(blob)
        except (ValueError, TypeError):
            return None
    if not isinstance(parsed, dict):
        return None
    error_type = str(parsed.get("error") or "UnknownError")
    message = str(parsed.get("message") or "")
    return error_type, message


def _langgraph_url() -> str:
    host = env_str("LANGGRAPH_HOST", "localhost")
    port = env_str("LANGGRAPH_PORT", "2024")
    return env_str("LANGGRAPH_URL", "") or f"http://{host}:{port}"


async def _fetch_errored_threads(client: httpx.AsyncClient, base: str) -> list[dict[str, Any]]:
    response = await client.post(
        f"{base}/threads/search",
        json={"limit": 20, "sort_by": "updated_at", "sort_order": "desc"},
        timeout=5,
    )
    response.raise_for_status()
    threads = response.json()
    if not isinstance(threads, list):
        return []
    return [t for t in threads if t.get("status") == "error"]


async def _latest_run_id(client: httpx.AsyncClient, base: str, thread_id: str) -> str | None:
    response = await client.get(f"{base}/threads/{thread_id}/runs", timeout=5)
    if response.status_code != 200:
        return None
    runs = response.json()
    if not isinstance(runs, list):
        return None
    for r in runs:
        if r.get("status") == "error":
            return r.get("run_id")
    return None


async def _notify_for_thread(
    client: httpx.AsyncClient, base: str, thread: dict[str, Any], notified: set[tuple[str, str]]
) -> None:
    thread_id = thread.get("thread_id")
    if not isinstance(thread_id, str):
        return

    run_id = await _latest_run_id(client, base, thread_id)
    if run_id is None:
        return  # No errored run found; nothing to attribute the error to.

    key = (thread_id, run_id)
    if key in notified:
        return

    decoded = _decode_error_blob(thread.get("error", ""))
    if decoded is None:
        notified.add(key)
        return  # Malformed error — mark notified so we don't loop.
    error_type, raw_message = decoded

    configurable = (thread.get("config") or {}).get("configurable") or {}
    body = _format_error_message(error_type, raw_message)
    body_slack = _format_error_message_slack(error_type, raw_message)

    success, channel = await post_to_source(
        configurable, body_markdown=body, body_slack_mrkdwn=body_slack
    )
    notified.add(key)  # Mark notified regardless of post success — avoid retry storms.
    if success:
        logger.info(
            "Posted run-error notification (thread=%s run=%s type=%s channel=%s)",
            thread_id[:8],
            run_id[:8],
            error_type,
            channel,
        )
    else:
        logger.warning(
            "Run errored but no source channel to notify (thread=%s run=%s type=%s)",
            thread_id[:8],
            run_id[:8],
            error_type,
        )


async def run_error_watcher_loop() -> None:
    """Poll the local LangGraph API for errored runs; notify the source channel.

    Cancellation-safe: catches `asyncio.CancelledError` to allow clean
    shutdown. Other exceptions per iteration are logged and ignored so a
    transient network blip doesn't kill the watcher.
    """
    interval = max(2, env_int("RUN_ERROR_POLL_INTERVAL_SECONDS", 10))
    base = _langgraph_url().rstrip("/")
    notified: set[tuple[str, str]] = set()

    logger.info("Run-error watcher started: polling %s every %ds", base, interval)

    # Brief initial delay so the FastAPI app finishes booting before
    # we hammer it with our own client.
    await asyncio.sleep(3)

    async with httpx.AsyncClient() as client:
        while True:
            try:
                errored = await _fetch_errored_threads(client, base)
                for thread in errored:
                    await _notify_for_thread(client, base, thread, notified)
            except asyncio.CancelledError:
                raise
            except httpx.HTTPError as exc:
                logger.debug("Run-error watcher poll failed: %s", exc)
            except Exception:
                logger.exception("Run-error watcher iteration failed")
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise
