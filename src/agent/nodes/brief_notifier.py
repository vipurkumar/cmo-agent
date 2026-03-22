"""Brief notifier — delivers seller briefs to sales reps via Slack.

Sends a polished, skimmable brief to the configured sales Slack channel.
Only sends for pursue_now and human_review_required actions.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
        raise RuntimeError("brief_notifier tools not initialised — call init_tools() first")
    return SlackApprovalTool(_rate_limiter)


def _action_emoji(action: ActionType) -> str:
    """Return the header emoji based on the action type."""
    if action == ActionType.HUMAN_REVIEW_REQUIRED:
        return "\u26a0\ufe0f"
    return "\U0001f3af"


def _action_badge(action: ActionType) -> str:
    """Return a human-readable badge label for the action."""
    return {
        ActionType.PURSUE_NOW: ":large_green_circle: Pursue Now",
        ActionType.HUMAN_REVIEW_REQUIRED: ":warning: Human Review Required",
        ActionType.NURTURE: ":hourglass_flowing_sand: Nurture",
        ActionType.DISQUALIFY: ":no_entry_sign: Disqualify",
    }.get(action, action.value)


def _build_blocks(state: QualificationState) -> list[dict]:
    """Build Slack Block Kit blocks for the seller brief notification."""
    account = state.get("current_account")
    company_name = account.company_name if account else "Unknown"
    account_id = account.id if account else "unknown"

    score = state.get("account_score")
    overall_score = score.overall_priority_score if score else 0
    confidence = score.confidence_score if score else 0.0
    scoring_version = score.scoring_version if score else "v1"

    recommendation = state.get("action_recommendation")
    action = recommendation.action if recommendation else ActionType.HUMAN_REVIEW_REQUIRED

    brief = state.get("seller_brief")

    emoji = _action_emoji(action)
    badge = _action_badge(action)

    blocks: list[dict] = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"{emoji} OmniGTM Brief: {company_name}",
            "emoji": True,
        },
    })

    # Account snapshot + overall score + action badge
    snapshot = brief.account_snapshot if brief else "No snapshot available"
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*Account Snapshot*\n{snapshot}\n\n"
                f"*Overall Score:* {overall_score}/100  |  *Action:* {badge}"
            ),
        },
    })

    # Why Now — signal summary
    signals = state.get("signals", [])
    if signals:
        signal_lines = []
        for sig in signals[:5]:
            date_str = sig.event_date.strftime("%Y-%m-%d") if sig.event_date else "N/A"
            signal_lines.append(
                f"\u2022 [{sig.signal_type.value}] {sig.observed_fact} ({date_str})"
            )
        why_now_text = "\n".join(signal_lines)
    else:
        why_now_text = "No recent signals detected"

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Why Now*\n{why_now_text}",
        },
    })

    # Top Contact
    ranked_contacts = state.get("ranked_contacts", [])
    if ranked_contacts:
        top = ranked_contacts[0]
        contact_text = (
            f"*Name:* {top.name}\n"
            f"*Title:* {top.title}\n"
            f"*Role:* {top.likely_role.value}\n"
            f"*Relevance:* {top.relevance_score}/100"
        )
    else:
        contact_text = "No contacts ranked"

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Top Contact*\n{contact_text}",
        },
    })

    # Pain Hypothesis — top pain + score
    pain_hypotheses = state.get("pain_hypotheses", [])
    if pain_hypotheses:
        top_pain = pain_hypotheses[0]
        pain_text = f"{top_pain.pain_type.value} (score: {top_pain.score}/100)"
    else:
        pain_text = "No pain hypotheses identified"

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Pain Hypothesis*\n{pain_text}",
        },
    })

    # Talk Track — one-line hook + value prop
    value_props = state.get("value_props", [])
    if value_props:
        top_vp = value_props[0]
        talk_text = (
            f"*Hook:* {top_vp.one_line_hook}\n"
            f"*Value Prop:* {top_vp.short_value_prop}"
        )
    else:
        talk_text = "No talk track generated"

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Talk Track*\n{talk_text}",
        },
    })

    # Context — confidence score, scoring version, timestamp
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f"Confidence: {confidence:.2f}  |  "
                    f"Scoring: {scoring_version}  |  "
                    f"Generated: {now_str}"
                ),
            },
        ],
    })

    # Actions — "View Full Brief" button
    blocks.append({
        "type": "actions",
        "block_id": f"brief_{account_id}",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Full Brief"},
                "url": f"/api/v1/accounts/{account_id}/brief",
                "action_id": "view_full_brief",
            },
        ],
    })

    return blocks


async def brief_notifier(state: QualificationState) -> dict:
    """Send formatted seller briefs to sales reps via Slack."""
    thread_id = state.get("thread_id", "")
    workspace_id = state.get("workspace_id", "")

    log.info("brief_notifier.start", thread_id=thread_id, workspace_id=workspace_id)

    recommendation = state.get("action_recommendation")

    # Only send for pursue_now and human_review_required actions
    if not recommendation or recommendation.action not in (
        ActionType.PURSUE_NOW,
        ActionType.HUMAN_REVIEW_REQUIRED,
    ):
        log.info(
            "brief_notifier.skipped",
            thread_id=thread_id,
            workspace_id=workspace_id,
            reason="action not pursue_now or human_review_required",
            action=recommendation.action.value if recommendation else "none",
        )
        return {}

    slack_tool = _get_tool()

    blocks = _build_blocks(state)

    account = state.get("current_account")
    company_name = account.company_name if account else "Unknown"

    # Build the message_draft with subject/body for the SlackApprovalTool
    # The blocks are sent as the rich message body
    emoji = _action_emoji(recommendation.action)
    message_draft = {
        "subject": f"{emoji} OmniGTM Brief: {company_name}",
        "body": f"Seller brief for {company_name}",
        "blocks": blocks,
    }

    # Get channel from campaign config
    campaign = state.get("campaign")
    channel = (
        campaign.sequence_config.get("sales_channel", "gtm-sales")
        if campaign and campaign.sequence_config
        else "gtm-sales"
    )

    plan_name = "pro"

    try:
        await slack_tool.run(
            message_draft=message_draft,
            workspace_id=workspace_id,
            plan=plan_name,
            channel=channel,
        )
        log.info(
            "brief_notifier.sent",
            thread_id=thread_id,
            workspace_id=workspace_id,
            channel=channel,
            action=recommendation.action.value,
        )
    except Exception as exc:
        log.error(
            "brief_notifier.error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )

    log.info("brief_notifier.complete", thread_id=thread_id, workspace_id=workspace_id)
    return {}
