"""Audit log API — workspace activity tracking."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select, func, desc

from src.api.deps import SessionDep, WorkspaceDep
from src.db.queries import (
    FeedbackEventRecord,
    SellerBriefRecord,
    AccountScoreRecord,
    Message,
)
from src.logger import log

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/activity")
async def get_activity_log(
    session: SessionDep,
    workspace_id: WorkspaceDep,
    limit: int = 50,
    offset: int = 0,
):
    """Get recent activity for the workspace — briefs, scores, messages, feedback."""
    log.info("api.audit_activity", workspace_id=workspace_id)

    activities = []

    # Recent briefs
    briefs_result = await session.execute(
        select(SellerBriefRecord)
        .where(SellerBriefRecord.workspace_id == workspace_id)
        .order_by(desc(SellerBriefRecord.generated_at))
        .limit(limit)
    )
    for b in briefs_result.scalars().all():
        activities.append({
            "type": "brief_generated",
            "id": b.id,
            "account_id": b.account_id,
            "action_type": b.action_type,
            "overall_score": b.overall_score,
            "timestamp": str(b.generated_at) if b.generated_at else None,
        })

    # Recent scores
    scores_result = await session.execute(
        select(AccountScoreRecord)
        .where(AccountScoreRecord.workspace_id == workspace_id)
        .order_by(desc(AccountScoreRecord.scored_at))
        .limit(limit)
    )
    for s in scores_result.scalars().all():
        activities.append({
            "type": "account_scored",
            "id": s.id,
            "account_id": s.account_id,
            "overall_priority_score": s.overall_priority_score,
            "is_disqualified": s.is_disqualified,
            "timestamp": str(s.scored_at) if s.scored_at else None,
        })

    # Recent feedback
    feedback_result = await session.execute(
        select(FeedbackEventRecord)
        .where(FeedbackEventRecord.workspace_id == workspace_id)
        .order_by(desc(FeedbackEventRecord.created_at))
        .limit(limit)
    )
    for f in feedback_result.scalars().all():
        activities.append({
            "type": "feedback_received",
            "id": f.id,
            "recommendation_id": f.recommendation_id,
            "action_taken": f.action_taken,
            "timestamp": str(f.created_at) if f.created_at else None,
        })

    # Sort all activities by timestamp descending
    activities.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

    return {
        "activities": activities[:limit],
        "total": len(activities),
        "workspace_id": workspace_id,
    }


@router.get("/summary")
async def get_workspace_summary(
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Get a high-level summary of workspace activity."""
    log.info("api.audit_summary", workspace_id=workspace_id)

    # Count briefs
    brief_count = (await session.execute(
        select(func.count(SellerBriefRecord.id))
        .where(SellerBriefRecord.workspace_id == workspace_id)
    )).scalar() or 0

    # Count scores
    score_count = (await session.execute(
        select(func.count(AccountScoreRecord.id))
        .where(AccountScoreRecord.workspace_id == workspace_id)
    )).scalar() or 0

    # Count feedback
    feedback_count = (await session.execute(
        select(func.count(FeedbackEventRecord.id))
        .where(FeedbackEventRecord.workspace_id == workspace_id)
    )).scalar() or 0

    # Action distribution
    action_dist_result = await session.execute(
        select(SellerBriefRecord.action_type, func.count(SellerBriefRecord.id))
        .where(SellerBriefRecord.workspace_id == workspace_id)
        .group_by(SellerBriefRecord.action_type)
    )
    action_distribution = {row[0]: row[1] for row in action_dist_result.all()}

    return {
        "workspace_id": workspace_id,
        "total_briefs": brief_count,
        "total_scores": score_count,
        "total_feedback": feedback_count,
        "action_distribution": action_distribution,
    }
