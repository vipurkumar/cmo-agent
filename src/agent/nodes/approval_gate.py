"""approval_gate node — sends the draft email to Slack for human approval.

Posts the draft via SlackApprovalTool and returns the approval status.
The actual approval/rejection is handled asynchronously via n8n webhooks
that resume the LangGraph thread.
"""

from __future__ import annotations

from src.agent.state import OutboundState
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.slack_approval import SlackApprovalTool

# Module-level tool — RateLimiter injected at startup
_rate_limiter: RateLimiter | None = None


def init_tools(rate_limiter: RateLimiter) -> None:
    """Inject the shared RateLimiter (called once at app startup)."""
    global _rate_limiter
    _rate_limiter = rate_limiter


def _get_tool() -> SlackApprovalTool:
    if _rate_limiter is None:
        raise RuntimeError("approval_gate tools not initialised — call init_tools() first")
    return SlackApprovalTool(_rate_limiter)


async def approval_gate(state: OutboundState) -> dict:
    """Send the draft email to Slack for human approval."""
    thread_id = state["thread_id"]
    account = state["current_account"]
    if account is None:
        return {"approval_status": "rejected", "error": "No current_account set"}

    workspace_id = account.workspace_id
    log.info("approval_gate.start", thread_id=thread_id, workspace_id=workspace_id)

    draft = state.get("draft_email")
    if draft is None:
        log.warning(
            "approval_gate.no_draft",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        return {"approval_status": "rejected", "error": "No draft email to approve"}

    slack_tool = _get_tool()

    # Build message payload for Slack
    message_draft = {
        "subject": draft.subject_line,
        "body": draft.body,
    }

    # Determine Slack channel from campaign config or workspace settings
    campaign = state.get("campaign")
    channel = (
        campaign.sequence_config.get("slack_channel", "")
        if campaign and campaign.sequence_config
        else ""
    )
    if not channel:
        channel = "approvals"  # fallback default channel

    plan_name = "pro"

    result = await slack_tool.run(
        message_draft=message_draft,
        workspace_id=workspace_id,
        plan=plan_name,
        channel=channel,
    )

    # The Slack tool posts the message and returns pending status.
    # The graph will be interrupted here, and an n8n webhook will
    # resume it with the actual approval_status once a human responds.
    status = result.get("status", "pending")

    log.info(
        "approval_gate.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        status=status,
    )

    return {"approval_status": status}
