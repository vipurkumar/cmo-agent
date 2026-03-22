"""Task creation node — creates seller tasks in HubSpot from briefs.

For pursue_now actions: creates a HubSpot task assigned to the account owner
with the brief summary, recommended contact, and suggested channel.

For human_review_required: creates a review task in a review queue.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.agent.state import ActionType, QualificationState
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.hubspot_tools import HubSpotTool

# Module-level tools — RateLimiter injected at startup
_rate_limiter: RateLimiter | None = None


def init_tools(rate_limiter: RateLimiter) -> None:
    """Inject the shared RateLimiter (called once at app startup)."""
    global _rate_limiter
    _rate_limiter = rate_limiter


def _get_hubspot() -> HubSpotTool:
    if _rate_limiter is None:
        raise RuntimeError("task_creator tools not initialised — call init_tools() first")
    return HubSpotTool(_rate_limiter)


def _add_business_days(start: datetime, days: int) -> datetime:
    """Return a datetime ``days`` business days after ``start``."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        # Monday=0 … Friday=4
        if current.weekday() < 5:
            added += 1
    return current


async def task_creator(state: QualificationState) -> dict:
    """Create follow-up tasks in HubSpot CRM from qualification results."""
    thread_id = state["thread_id"]
    account = state.get("current_account")
    if account is None:
        return {}

    workspace_id = account.workspace_id
    log.info("task_creator.start", thread_id=thread_id, workspace_id=workspace_id)

    action_recommendation = state.get("action_recommendation")
    if action_recommendation is None:
        log.info(
            "task_creator.skip_no_recommendation",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        return {}

    action = action_recommendation.action

    # Only create tasks for pursue_now and human_review_required
    if action not in (ActionType.PURSUE_NOW, ActionType.HUMAN_REVIEW_REQUIRED):
        log.info(
            "task_creator.skip_action",
            thread_id=thread_id,
            workspace_id=workspace_id,
            action=action.value,
        )
        return {}

    seller_brief = state.get("seller_brief")
    hubspot_tool = _get_hubspot()
    plan_name = "pro"
    now = datetime.now(timezone.utc)

    if action == ActionType.PURSUE_NOW:
        # Build contact info
        best_contact = action_recommendation.best_first_contact
        contact_name = best_contact.name if best_contact else "Unknown"
        contact_title = best_contact.title if best_contact else ""
        suggested_channel = action_recommendation.best_channel or "email"

        task_subject = f"OmniGTM: Pursue {account.company_name} — {contact_name}"

        body_parts = []
        if seller_brief:
            body_parts.append(f"Account Snapshot:\n{seller_brief.account_snapshot}")
            body_parts.append(f"\nWhy Now:\n{seller_brief.why_now}")
        body_parts.append(f"\nRecommended Contact: {contact_name} ({contact_title})")
        body_parts.append(f"Suggested Channel: {suggested_channel}")
        body_parts.append(f"Explanation: {action_recommendation.explanation}")
        task_body = "\n".join(body_parts)

        due_date = _add_business_days(now, 2)
        priority = "HIGH"
        task_type = "SALES"

    else:  # HUMAN_REVIEW_REQUIRED
        task_subject = (
            f"OmniGTM Review: {account.company_name} — low confidence"
        )

        body_parts = [
            f"Account: {account.company_name}",
            f"Confidence: {action_recommendation.confidence_score}",
            f"Explanation: {action_recommendation.explanation}",
        ]
        if seller_brief:
            body_parts.append(f"\nAccount Snapshot:\n{seller_brief.account_snapshot}")
        task_body = "\n".join(body_parts)

        due_date = _add_business_days(now, 5)
        priority = "MEDIUM"
        task_type = "REVIEW"

    try:
        await hubspot_tool.run(
            operation="create",
            workspace_id=workspace_id,
            plan=plan_name,
            object_type="tasks",
            properties={
                "hs_task_subject": task_subject,
                "hs_task_body": task_body,
                "hs_task_priority": priority,
                "hs_task_type": task_type,
                "hs_timestamp": due_date.isoformat(),
                "hs_company_id": account.metadata.get(
                    "hubspot_company_id", account.id
                ),
            },
        )
        log.info(
            "task_creator.task_created",
            thread_id=thread_id,
            workspace_id=workspace_id,
            action=action.value,
            task_type=task_type,
        )
    except Exception as exc:
        log.error(
            "task_creator.hubspot_error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )

    log.info("task_creator.complete", thread_id=thread_id, workspace_id=workspace_id)
    return {}
