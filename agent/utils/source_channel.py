"""Post a message to whichever source channel triggered the run.

Reads `config["configurable"]["source"]` and dispatches to the matching
channel helper. Returns `(success, channel)` where `channel` is one of
`linear`, `slack`, `github`, or `none`.
"""

from __future__ import annotations

import logging
from typing import Any

from .github_app import get_github_app_installation_token
from .github_comments import post_github_comment
from .linear import comment_on_linear_issue
from .slack import convert_mentions_to_slack_format, post_slack_thread_reply

logger = logging.getLogger(__name__)


async def post_to_source(
    configurable: dict[str, Any],
    body_markdown: str,
    body_slack_mrkdwn: str | None = None,
) -> tuple[bool, str]:
    """Post a comment to the source channel inferred from `configurable`.

    Args:
        configurable: The `config["configurable"]` dict for the run.
        body_markdown: GitHub-Flavored Markdown body. Used for Linear and
            GitHub.
        body_slack_mrkdwn: Optional Slack mrkdwn variant. If omitted,
            `body_markdown` is reused — usually fine for short bodies but
            heavy markdown will not render correctly in Slack.

    Returns:
        Tuple of `(success, channel)`.
    """
    source = configurable.get("source", "")

    if source == "linear":
        issue_id = configurable.get("linear_issue", {}).get("id", "")
        if not issue_id:
            return False, "linear"
        ok = await comment_on_linear_issue(issue_id, body_markdown)
        return ok, "linear"

    if source == "slack":
        slack_thread = configurable.get("slack_thread", {})
        channel_id = slack_thread.get("channel_id")
        thread_ts = slack_thread.get("thread_ts")
        if not channel_id or not thread_ts:
            return False, "slack"
        body = body_slack_mrkdwn if body_slack_mrkdwn is not None else body_markdown
        body = convert_mentions_to_slack_format(body)
        ok = await post_slack_thread_reply(channel_id, thread_ts, body)
        return ok, "slack"

    if source == "github":
        repo_config = configurable.get("repo", {})
        issue_number = configurable.get("github_issue", {}).get("number") or configurable.get(
            "pr_number"
        )
        if not repo_config or not issue_number:
            return False, "github"
        token = await get_github_app_installation_token()
        if not token:
            return False, "github"
        ok = await post_github_comment(repo_config, int(issue_number), body_markdown, token=token)
        return ok, "github"

    return False, "none"
