"""Data export endpoints — CSV and JSON export for customer data."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter
from sqlalchemy import select
from starlette.responses import StreamingResponse

from src.api.deps import SessionDep, WorkspaceDep
from src.db.queries import AccountScoreRecord, SellerBriefRecord
from src.logger import log

router = APIRouter(tags=["export"])


@router.get("/api/v1/export/briefs")
async def export_briefs(
    session: SessionDep,
    workspace_id: WorkspaceDep,
    format: str = "json",
    action_type: str | None = None,
    limit: int = 100,
):
    """Export seller briefs as JSON or CSV."""
    log.info("api.export_briefs", workspace_id=workspace_id, format=format)

    stmt = (
        select(SellerBriefRecord)
        .where(SellerBriefRecord.workspace_id == workspace_id)
        .order_by(SellerBriefRecord.generated_at.desc())
        .limit(limit)
    )
    if action_type:
        stmt = stmt.where(SellerBriefRecord.action_type == action_type)

    result = await session.execute(stmt)
    briefs = result.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "brief_id", "account_id", "action_type", "overall_score",
            "confidence_score", "version", "generated_at",
        ])
        for b in briefs:
            writer.writerow([
                b.id, b.account_id, b.action_type, b.overall_score,
                b.confidence_score, b.version, b.generated_at,
            ])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=briefs_{workspace_id}.csv",
            },
        )

    return [
        {
            "brief_id": b.id,
            "account_id": b.account_id,
            "action_type": b.action_type,
            "overall_score": b.overall_score,
            "confidence_score": b.confidence_score,
            "version": b.version,
            "brief": b.brief_json,
            "generated_at": str(b.generated_at) if b.generated_at else None,
        }
        for b in briefs
    ]


@router.get("/api/v1/export/scores")
async def export_scores(
    session: SessionDep,
    workspace_id: WorkspaceDep,
    format: str = "json",
    limit: int = 100,
):
    """Export account scores as JSON or CSV."""
    log.info("api.export_scores", workspace_id=workspace_id, format=format)

    result = await session.execute(
        select(AccountScoreRecord)
        .where(AccountScoreRecord.workspace_id == workspace_id)
        .order_by(AccountScoreRecord.scored_at.desc())
        .limit(limit)
    )
    scores = result.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "account_id", "icp_fit", "pain_fit", "timing",
            "overall_priority", "confidence", "is_disqualified", "scored_at",
        ])
        for s in scores:
            writer.writerow([
                s.account_id, s.icp_fit_score, s.pain_fit_score,
                s.timing_score, s.overall_priority_score, s.confidence_score,
                s.is_disqualified, s.scored_at,
            ])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=scores_{workspace_id}.csv",
            },
        )

    return [
        {
            "account_id": s.account_id,
            "icp_fit_score": s.icp_fit_score,
            "pain_fit_score": s.pain_fit_score,
            "timing_score": s.timing_score,
            "overall_priority_score": s.overall_priority_score,
            "confidence_score": s.confidence_score,
            "is_disqualified": s.is_disqualified,
            "scored_at": str(s.scored_at) if s.scored_at else None,
        }
        for s in scores
    ]
