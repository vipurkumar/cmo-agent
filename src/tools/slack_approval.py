"""SlackApprovalTool — sends approval request to Slack and waits for response."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class SlackRateLimitError(Exception):
    """Raised when the Slack API returns HTTP 429."""


class SlackAuthError(Exception):
    """Raised when the Slack API returns HTTP 401."""


SLACK_API_BASE = "https://slack.com/api"


class SlackApprovalTool(BaseTool):
    """Sends an approval request to a Slack channel and waits for response.

    Input: message_draft, workspace_id, channel.
    Output: approval status dict.
    """

    RESOURCE_NAME = "slack"

    def __init__(self, rate_limiter: RateLimiter) -> None:
        super().__init__(rate_limiter)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def run(
        self,
        message_draft: dict[str, str],
        workspace_id: str,
        plan: str,
        channel: str,
    ) -> dict[str, Any]:
        """Send an approval request to Slack.

        This posts a message with interactive approval buttons to the
        specified Slack channel. The actual approval/rejection callback
        is handled asynchronously via n8n webhooks.

        Parameters
        ----------
        message_draft:
            Dict with ``subject`` and ``body`` keys to present for approval.
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace.
        channel:
            Slack channel ID to post the approval request to.

        Returns
        -------
        dict[str, Any]
            ``{"status": "pending", "message_ts": "...", "channel": "..."}``
        """
        log.info(
            "slack_approval.start",
            workspace_id=workspace_id,
            channel=channel,
        )

        # 1. Rate limit check FIRST
        await self.rate_limiter.enforce(workspace_id, self.RESOURCE_NAME, plan)

        # 2. Build the Slack message with approval buttons
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Email Approval Request*\n\n"
                        f"*Subject:* {message_draft.get('subject', 'N/A')}\n\n"
                        f"*Body:*\n{message_draft.get('body', 'N/A')}"
                    ),
                },
            },
            {
                "type": "actions",
                "block_id": f"approval_{workspace_id}",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": "approve_email",
                        "value": workspace_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": "reject_email",
                        "value": workspace_id,
                    },
                ],
            },
        ]

        # 3. HTTP call with timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "channel": channel,
                    "blocks": blocks,
                    "text": "Email approval request",
                },
            )

        # 4. Specific error handling
        if resp.status_code == 429:
            raise SlackRateLimitError(
                f"Rate limited by Slack API for workspace {workspace_id}"
            )
        if resp.status_code == 401:
            raise SlackAuthError("Invalid Slack bot token")
        resp.raise_for_status()

        data = resp.json()

        if not data.get("ok"):
            log.error(
                "slack_approval.api_error",
                workspace_id=workspace_id,
                error=data.get("error", "unknown"),
            )
            return {"status": "error", "error": data.get("error", "unknown")}

        result: dict[str, Any] = {
            "status": "pending",
            "message_ts": data.get("ts", ""),
            "channel": channel,
        }

        log.info(
            "slack_approval.complete",
            workspace_id=workspace_id,
            message_ts=result["message_ts"],
        )

        return result
