"""Post a role-transition announcement to the source channel."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langgraph.config import get_config

from ..utils.roles import get_role_display_name, load_roles
from ..utils.source_channel import post_to_source

logger = logging.getLogger(__name__)

_VALID_PHASES = ("starting", "done")


def _format_message(display: str, phase: str, summary: str, *, slack: bool) -> str:
    bold_open, bold_close = ("*", "*") if slack else ("**", "**")
    summary = summary.strip()
    if phase == "starting":
        return f"{bold_open}{display}{bold_close} — starting: {summary}"
    return f"{bold_open}{display}{bold_close} — done: {summary}"


def role_status(role: str, phase: str, summary: str) -> dict[str, Any]:
    """Announce that you are entering or leaving a role.

    Call this whenever you take on or hand off a role from
    `evalgenie-build-team/roles/`. Posts a short status comment to the
    source channel (Linear / Slack / GitHub) so reviewers can see who is
    doing what — e.g. "QA Manager — starting: writing test plan for
    auth flow" then "QA Manager — done: TEST_PLAN.md drafted".

    Use this for *role transitions only*, not for every step. The agent
    that triggered the run is the same Linear/Slack/GitHub channel that
    receives these announcements.

    Args:
        role: Role slug from `evalgenie-build-team/roles/` (e.g.
            `qa-manager`, `architect`, `release-manager`).
        phase: `"starting"` when the role begins work; `"done"` when the
            role hands off or completes its artifact.
        summary: One short sentence describing the role's intent
            (`starting`) or what it produced (`done`). Keep under ~140
            chars; this is a status ping, not the deliverable itself.

    Returns:
        Dict with `success` (bool), `role_display` (str), `channel`
        (`linear` | `slack` | `github` | `none`), and `error` (str) when
        unsuccessful.
    """
    if phase not in _VALID_PHASES:
        return {
            "success": False,
            "error": f"Invalid phase '{phase}'. Must be one of: {', '.join(_VALID_PHASES)}.",
        }
    if not summary.strip():
        return {"success": False, "error": "summary cannot be empty"}

    display = get_role_display_name(role)
    if display is None:
        known = ", ".join(sorted(load_roles())) or "<no roles configured>"
        return {
            "success": False,
            "error": f"Unknown role '{role}'. Known roles: {known}.",
        }

    configurable = get_config().get("configurable", {})
    success, channel = asyncio.run(
        post_to_source(
            configurable,
            body_markdown=_format_message(display, phase, summary, slack=False),
            body_slack_mrkdwn=_format_message(display, phase, summary, slack=True),
        )
    )

    if not success:
        logger.warning(
            "role_status announcement failed (role=%s phase=%s channel=%s)", role, phase, channel
        )
        return {
            "success": False,
            "role_display": display,
            "channel": channel,
            "error": (
                f"Failed to post {phase} announcement to {channel}. "
                "Check that the run has source-channel context (linear_issue / slack_thread / "
                "github_issue or pr_number)."
            ),
        }

    return {"success": True, "role_display": display, "channel": channel}
