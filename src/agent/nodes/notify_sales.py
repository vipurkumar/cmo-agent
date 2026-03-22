"""notify_sales node — alerts the sales team about a positive reply.

Sends a Slack notification and syncs the engagement to HubSpot CRM.
"""

from __future__ import annotations

from src.agent.state import OutboundState
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.hubspot_tools import HubSpotTool
from src.tools.slack_approval import SlackApprovalTool

# Module-level tools — RateLimiter injected at startup
_rate_limiter: RateLimiter | None = None


def init_tools(rate_limiter: RateLimiter) -> None:
    """Inject the shared RateLimiter (called once at app startup)."""
    global _rate_limiter
    _rate_limiter = rate_limiter


def _get_tools() -> tuple[SlackApprovalTool, HubSpotTool]:
    if _rate_limiter is None:
        raise RuntimeError("notify_sales tools not initialised — call init_tools() first")
    return SlackApprovalTool(_rate_limiter), HubSpotTool(_rate_limiter)


async def notify_sales(state: OutboundState) -> dict:
    """Notify sales team via Slack and sync to HubSpot."""
    thread_id = state["thread_id"]
    account = state["current_account"]
    if account is None:
        return {}

    workspace_id = account.workspace_id
    log.info("notify_sales.start", thread_id=thread_id, workspace_id=workspace_id)

    contact = state.get("current_contact")
    reply = state.get("reply_analysis")
    campaign = state.get("campaign")

    slack_tool, hubspot_tool = _get_tools()
    plan_name = "pro"

    # 1. Send Slack notification to sales channel
    notification = {
        "subject": f"Positive Reply from {account.company_name}",
        "body": (
            f"Contact: {contact.first_name or ''} {contact.last_name or ''} ({contact.email})\n"
            f"Company: {account.company_name}\n"
            f"Reply Intent: {reply.intent if reply else 'N/A'}\n"
            f"Confidence: {reply.confidence if reply else 0}\n"
            f"Reasoning: {reply.reasoning if reply else 'N/A'}\n"
            f"Suggested Action: {reply.suggested_action if reply else 'N/A'}"
        ) if contact else f"Positive reply from {account.company_name}",
    }

    # Determine sales notification channel
    channel = (
        campaign.sequence_config.get("sales_channel", "sales-alerts")
        if campaign and campaign.sequence_config
        else "sales-alerts"
    )

    try:
        await slack_tool.run(
            message_draft=notification,
            workspace_id=workspace_id,
            plan=plan_name,
            channel=channel,
        )
        log.info(
            "notify_sales.slack_sent",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
    except Exception as exc:
        log.error(
            "notify_sales.slack_error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )

    # 2. Sync to HubSpot — log activity on the contact
    if contact:
        try:
            await hubspot_tool.run(
                operation="log_activity",
                workspace_id=workspace_id,
                plan=plan_name,
                object_type="engagements",
                properties={
                    "hs_engagement_type": "NOTE",
                    "hs_note_body": (
                        f"Positive reply received from {contact.email} "
                        f"for campaign {campaign.name if campaign else 'N/A'}. "
                        f"Intent: {reply.intent if reply else 'unknown'}, "
                        f"Confidence: {reply.confidence if reply else 0}"
                    ),
                },
            )
            log.info(
                "notify_sales.hubspot_synced",
                thread_id=thread_id,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            log.error(
                "notify_sales.hubspot_error",
                thread_id=thread_id,
                workspace_id=workspace_id,
                error=str(exc),
            )

    log.info("notify_sales.complete", thread_id=thread_id, workspace_id=workspace_id)
    return {}
