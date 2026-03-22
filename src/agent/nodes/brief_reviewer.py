"""Brief review node — sends briefs to Slack for human approval.

For human_review_required actions, sends a formatted brief summary to a
Slack review channel. The graph interrupts and waits for approval via
webhook callback.

For pursue_now with manager_approval_required, also sends for review.
"""

from __future__ import annotations

from src.agent.state import ActionType, QualificationState
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
        raise RuntimeError("brief_reviewer tools not initialised — call init_tools() first")
    return SlackApprovalTool(_rate_limiter)


def _build_review_message(state: QualificationState) -> dict[str, str]:
    """Build a formatted Slack message summarising the brief for review."""
    account = state.get("current_account")
    account_name = account.company_name if account else "Unknown"

    score = state.get("account_score")
    priority_score = score.overall_priority_score if score else 0

    recommendation = state.get("action_recommendation")
    action_label = recommendation.action.value if recommendation else "unknown"
    explanation = recommendation.explanation if recommendation else "No explanation"

    # Top 3 pain hypotheses
    pain_hypotheses = state.get("pain_hypotheses", [])
    pain_lines: list[str] = []
    for ph in pain_hypotheses[:3]:
        pain_lines.append(f"  • {ph.pain_type.value} (score: {ph.score})")
    pain_section = "\n".join(pain_lines) if pain_lines else "  None identified"

    # Top contact recommendation
    ranked_contacts = state.get("ranked_contacts", [])
    if ranked_contacts:
        top = ranked_contacts[0]
        contact_section = f"  {top.name} — {top.title} (relevance: {top.relevance_score})"
    else:
        contact_section = "  No contacts ranked"

    subject = f"Brief Review: {account_name} — {action_label}"
    body = (
        f"*Account:* {account_name}\n"
        f"*Priority Score:* {priority_score}\n\n"
        f"*Recommended Action:* {action_label}\n"
        f"*Explanation:* {explanation}\n\n"
        f"*Top Pain Hypotheses:*\n{pain_section}\n\n"
        f"*Top Contact:*\n{contact_section}\n\n"
        f"Please approve, reject, or override this recommendation."
    )

    return {"subject": subject, "body": body}


async def brief_reviewer(state: QualificationState) -> dict:
    """Send briefs requiring human review to Slack for approval."""
    thread_id = state.get("thread_id", "")
    workspace_id = state.get("workspace_id", "")

    log.info("brief_reviewer.start", thread_id=thread_id, workspace_id=workspace_id)

    recommendation = state.get("action_recommendation")

    # Auto-approve pursue_now that does NOT require manager approval
    if recommendation and recommendation.action == ActionType.PURSUE_NOW:
        if not recommendation.manager_approval_required:
            log.info(
                "brief_reviewer.auto_approved",
                thread_id=thread_id,
                workspace_id=workspace_id,
                action=recommendation.action.value,
            )
            return {"approval_status": "auto_approved"}

    # All other cases: human_review_required, or pursue_now with
    # manager_approval_required — send to Slack for review
    slack_tool = _get_tool()

    message_draft = _build_review_message(state)

    # Get review channel from campaign config
    campaign = state.get("campaign")
    channel = (
        campaign.sequence_config.get("review_channel", "gtm-reviews")
        if campaign and campaign.sequence_config
        else "gtm-reviews"
    )

    plan_name = "pro"

    result = await slack_tool.run(
        message_draft=message_draft,
        workspace_id=workspace_id,
        plan=plan_name,
        channel=channel,
    )

    status = result.get("status", "pending_review")

    log.info(
        "brief_reviewer.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        status=status,
    )

    return {"approval_status": "pending_review"}
