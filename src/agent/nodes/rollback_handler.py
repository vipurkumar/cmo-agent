"""Rollback handler — pause, resume, and undo automation.

Provides functions (not a LangGraph node) that API endpoints call to:
- Pause automation for a workspace
- Resume automation for a workspace
- List recent automated actions
- Mark automated actions for review
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.queries import FeedbackEventRecord, SellerBriefRecord
from src.guardrails.kill_switch import KillSwitch
from src.guardrails.send_caps import SendCapEnforcer
from src.logger import log


async def pause_automation(
    redis_client,
    workspace_id: str,
    reason: str,
) -> dict:
    """Pause automation for a workspace using the kill switch.

    Args:
        redis_client: Async Redis client.
        workspace_id: The workspace to pause.
        reason: Human-readable reason for the pause.

    Returns:
        Status dict with workspace_id, is_paused, and reason.
    """
    kill_switch = KillSwitch(redis_client)

    try:
        await kill_switch.pause_workspace(workspace_id, reason)
        log.info(
            "rollback.pause_automation",
            workspace_id=workspace_id,
            reason=reason,
        )
        return {
            "workspace_id": workspace_id,
            "is_paused": True,
            "reason": reason,
            "status": "paused",
        }
    except Exception as exc:
        log.error(
            "rollback.pause_error",
            workspace_id=workspace_id,
            error=str(exc),
        )
        return {
            "workspace_id": workspace_id,
            "is_paused": False,
            "reason": f"Failed to pause: {exc}",
            "status": "error",
        }


async def resume_automation(
    redis_client,
    workspace_id: str,
) -> dict:
    """Resume automation for a workspace.

    Args:
        redis_client: Async Redis client.
        workspace_id: The workspace to resume.

    Returns:
        Status dict with workspace_id, is_paused, and status.
    """
    kill_switch = KillSwitch(redis_client)

    try:
        await kill_switch.resume_workspace(workspace_id)
        log.info(
            "rollback.resume_automation",
            workspace_id=workspace_id,
        )
        return {
            "workspace_id": workspace_id,
            "is_paused": False,
            "reason": "",
            "status": "resumed",
        }
    except Exception as exc:
        log.error(
            "rollback.resume_error",
            workspace_id=workspace_id,
            error=str(exc),
        )
        return {
            "workspace_id": workspace_id,
            "is_paused": True,
            "reason": f"Failed to resume: {exc}",
            "status": "error",
        }


async def get_automation_status(
    redis_client,
    workspace_id: str,
) -> dict:
    """Get combined automation status for a workspace.

    Merges kill switch status with send cap remaining budget.

    Args:
        redis_client: Async Redis client.
        workspace_id: The workspace to check.

    Returns:
        Combined status dict with pause state and send cap remaining.
    """
    kill_switch = KillSwitch(redis_client)
    send_caps = SendCapEnforcer(redis_client)

    try:
        ks_status = await kill_switch.get_status(workspace_id)
    except Exception as exc:
        log.error(
            "rollback.kill_switch_status_error",
            workspace_id=workspace_id,
            error=str(exc),
        )
        ks_status = {
            "workspace_id": workspace_id,
            "is_paused": False,
            "reason": f"Unable to check: {exc}",
            "global_pause": False,
            "workspace_pause": False,
        }

    try:
        caps_remaining = await send_caps.get_remaining(workspace_id)
    except Exception as exc:
        log.error(
            "rollback.send_caps_status_error",
            workspace_id=workspace_id,
            error=str(exc),
        )
        caps_remaining = {
            "daily_remaining": -1,
            "weekly_remaining": -1,
            "daily_used": -1,
            "weekly_used": -1,
        }

    return {
        **ks_status,
        **caps_remaining,
    }


async def list_recent_auto_actions(
    session: AsyncSession,
    workspace_id: str,
    limit: int = 50,
) -> list[dict]:
    """List recent automated outbound actions for a workspace.

    Queries SellerBriefRecord where action_type = 'pursue_now',
    ordered by generated_at descending.

    Args:
        session: Async SQLAlchemy session.
        workspace_id: Tenant filter.
        limit: Maximum number of results (default 50).

    Returns:
        List of brief summary dicts.
    """
    try:
        result = await session.execute(
            select(SellerBriefRecord)
            .where(SellerBriefRecord.workspace_id == workspace_id)
            .where(SellerBriefRecord.action_type == "pursue_now")
            .order_by(SellerBriefRecord.generated_at.desc())
            .limit(limit)
        )
        records = result.scalars().all()

        return [
            {
                "brief_id": r.id,
                "account_id": r.account_id,
                "version": r.version,
                "action_type": r.action_type,
                "overall_score": r.overall_score,
                "confidence_score": r.confidence_score,
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            }
            for r in records
        ]
    except Exception as exc:
        log.error(
            "rollback.list_actions_error",
            workspace_id=workspace_id,
            error=str(exc),
        )
        return []


async def mark_for_review(
    session: AsyncSession,
    brief_id: str,
    workspace_id: str,
    reviewer: str,
) -> dict:
    """Mark an automated action for human review.

    Creates a FeedbackEvent with action_taken='flagged_for_review'.

    Args:
        session: Async SQLAlchemy session.
        brief_id: The brief to flag.
        workspace_id: Tenant filter.
        reviewer: The user flagging the brief.

    Returns:
        Confirmation dict with feedback_id.
    """
    try:
        record = FeedbackEventRecord(
            id=str(uuid4()),
            workspace_id=workspace_id,
            recommendation_id=brief_id,
            recommendation_type="seller_brief",
            user_id=reviewer,
            action_taken="flagged_for_review",
        )
        session.add(record)
        await session.flush()

        log.info(
            "rollback.marked_for_review",
            workspace_id=workspace_id,
            brief_id=brief_id,
            reviewer=reviewer,
            feedback_id=record.id,
        )
        return {
            "feedback_id": record.id,
            "brief_id": brief_id,
            "status": "flagged_for_review",
            "reviewer": reviewer,
        }
    except Exception as exc:
        log.error(
            "rollback.mark_review_error",
            workspace_id=workspace_id,
            brief_id=brief_id,
            error=str(exc),
        )
        return {
            "feedback_id": None,
            "brief_id": brief_id,
            "status": "error",
            "reason": str(exc),
        }
