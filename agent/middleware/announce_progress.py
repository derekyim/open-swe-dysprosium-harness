"""After-model hook that announces a PR as the Engineering Manager.

Every successful ``commit_and_open_pr`` triggers a single guaranteed
comment to the source channel attributed to the Engineering Manager
role, e.g.::

    **Engineering Manager** — PR opened: https://github.com/.../pull/15

This runs every model step but is a no-op once the PR URL has already
been announced for the thread, so it costs nothing on subsequent steps.
"""

from __future__ import annotations

import json as _json
import logging
from collections import defaultdict
from typing import Any

from langchain.agents.middleware import AgentState, after_model
from langgraph.config import get_config
from langgraph.runtime import Runtime

from ..utils.source_channel import post_to_source

logger = logging.getLogger(__name__)

# Module-level dedup: which PR URLs have already been EM-announced per thread.
# Lost on server restart, which is fine — restarts are rare and a duplicate
# announcement is benign. Keyed by thread_id for isolation across runs.
_EM_ANNOUNCED: dict[str, set[str]] = defaultdict(set)

_EM_ROLE_DISPLAY = "Engineering Manager"


def _field(msg: Any, name: str, default: Any = None) -> Any:
    if isinstance(msg, dict):
        return msg.get(name, default)
    return getattr(msg, name, default)


def _latest_successful_pr(messages: list) -> tuple[str, str] | None:
    """Find the most recent successful commit_and_open_pr.

    Returns `(pr_url, pr_title)` or `None`. The title comes from the
    matching AI tool-call's args; we look it up so the announcement can
    include the PR title as flavor.
    """
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if _field(m, "name") != "commit_and_open_pr":
            continue
        content = _field(m, "content", "")
        try:
            parsed = _json.loads(content) if isinstance(content, str) else content
        except (ValueError, TypeError):
            continue
        if not (isinstance(parsed, dict) and parsed.get("success") and parsed.get("pr_url")):
            continue

        pr_url = parsed["pr_url"]
        pr_title = ""
        tcid = _field(m, "tool_call_id")
        if tcid:
            for j in range(i):
                ai = messages[j]
                for tc in _field(ai, "tool_calls") or []:
                    raw_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                    if raw_id != tcid:
                        continue
                    args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                    if isinstance(args, dict):
                        pr_title = args.get("title", "") or ""
        return pr_url, pr_title
    return None


@after_model
async def announce_progress_if_needed(
    state: AgentState,
    runtime: Runtime,
) -> dict[str, Any] | None:
    """Post `**Engineering Manager** — PR opened: <url>` exactly once per PR URL."""
    try:
        messages = state.get("messages", [])
        info = _latest_successful_pr(messages)
        if info is None:
            return None
        pr_url, pr_title = info

        config = get_config()
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id") or "unknown"
        if pr_url in _EM_ANNOUNCED[thread_id]:
            return None

        body = f"**{_EM_ROLE_DISPLAY}** — PR opened: {pr_url}"
        body_slack = f"*{_EM_ROLE_DISPLAY}* — PR opened: <{pr_url}|{pr_url}>"
        if pr_title:
            body += f"\n\n_{pr_title}_"
            body_slack += f"\n\n_{pr_title}_"

        success, channel = await post_to_source(
            configurable, body_markdown=body, body_slack_mrkdwn=body_slack
        )
        if success:
            _EM_ANNOUNCED[thread_id].add(pr_url)
            logger.info("Posted EM PR announcement to %s for %s", channel, pr_url)
        else:
            logger.warning(
                "EM PR announcement failed (thread=%s channel=%s pr=%s)",
                thread_id,
                channel,
                pr_url,
            )
    except Exception:
        logger.exception("announce_progress_if_needed failed")
    return None
