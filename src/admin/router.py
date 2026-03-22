"""Admin API router for OmniGTM configuration management.

Provides endpoints for GTM Ops to configure ICP weights, thresholds,
knowledge base, and view system status.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from src.api.deps import SessionDep, WorkspaceDep
from src.config.action_thresholds import ACTION_THRESHOLDS, CONFIDENCE_LEVELS, SIGNAL_DECAY
from src.config.automation import (
    AUTO_OUTBOUND_THRESHOLDS,
    AUTOMATION_DEFAULTS,
    BLOCKLIST_CONFIG,
    KILL_SWITCH,
    ROLLBACK_CONFIG,
    SEND_CAPS,
)
from src.config.icp import DEFAULT_ICP, ICP_WEIGHTS
from src.db.queries import (
    AccountScoreRecord,
    FeedbackEventRecord,
    SellerBriefRecord,
    WorkspaceSettings,
    get_workspace_settings,
)
from src.logger import log

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_html_path = Path(__file__).parent / "ui.html"


# ---------------------------------------------------------------------------
# Request / response schemas (admin-specific, kept local per API convention)
# ---------------------------------------------------------------------------


class ICPConfigResponse(BaseModel):
    weights: dict[str, float]
    criteria: dict[str, Any]


class ICPConfigUpdateRequest(BaseModel):
    weights: dict[str, float] | None = None
    criteria: dict[str, Any] | None = None


class ThresholdsResponse(BaseModel):
    action_thresholds: dict[str, Any]
    confidence_levels: dict[str, float]
    signal_decay: dict[str, int]


class ThresholdsUpdateRequest(BaseModel):
    action_thresholds: dict[str, Any] | None = None
    confidence_levels: dict[str, float] | None = None
    signal_decay: dict[str, int] | None = None


class AutomationConfigResponse(BaseModel):
    defaults: dict[str, Any]
    auto_outbound_thresholds: dict[str, Any]
    send_caps: dict[str, int]
    blocklist: dict[str, bool]
    kill_switch: dict[str, Any]
    rollback: dict[str, Any]


class AutomationConfigUpdateRequest(BaseModel):
    defaults: dict[str, Any] | None = None
    auto_outbound_thresholds: dict[str, Any] | None = None
    send_caps: dict[str, int] | None = None
    blocklist: dict[str, bool] | None = None
    kill_switch: dict[str, Any] | None = None


class DashboardStatsResponse(BaseModel):
    total_accounts_scored: int = 0
    action_distribution: dict[str, int] = Field(default_factory=dict)
    average_overall_score: float = 0.0
    average_confidence: float = 0.0
    recent_briefs_count: int = 0
    feedback_summary: dict[str, int] = Field(default_factory=dict)


class BriefSummary(BaseModel):
    brief_id: str
    account_id: str
    action_type: str
    overall_score: int
    confidence_score: float
    version: int
    generated_at: str


class KBFileInfo(BaseModel):
    filename: str
    file_type: str
    size_bytes: int
    path: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deep_merge(base: dict, overrides: dict) -> dict:
    """Recursively merge overrides into base dict."""
    result = dict(base)
    for key, val in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


async def _get_settings_data(session: SessionDep, workspace_id: str) -> dict[str, Any]:
    """Load workspace settings_data, returning empty dict if none exist."""
    ws = await get_workspace_settings(session, workspace_id)
    if ws and ws.settings_data:
        return dict(ws.settings_data)
    return {}


async def _save_settings_data(
    session: SessionDep,
    workspace_id: str,
    data: dict[str, Any],
) -> None:
    """Upsert workspace settings_data."""
    ws = await get_workspace_settings(session, workspace_id)
    if ws:
        ws.settings_data = data
    else:
        ws = WorkspaceSettings(workspace_id=workspace_id, settings_data=data)
        session.add(ws)
    await session.flush()


# ---------------------------------------------------------------------------
# Admin UI
# ---------------------------------------------------------------------------


@router.get("/ui", response_class=HTMLResponse)
async def admin_ui():
    """Serve the admin dashboard UI."""
    return HTMLResponse(content=_admin_html_path.read_text())


# ---------------------------------------------------------------------------
# ICP Config
# ---------------------------------------------------------------------------


@router.get("/config/icp", response_model=ICPConfigResponse)
async def get_icp_config(
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Return current ICP weights and criteria (workspace overrides merged with defaults)."""
    log.info("admin.get_icp_config", workspace_id=workspace_id)
    settings_data = await _get_settings_data(session, workspace_id)

    weights = _deep_merge(dict(ICP_WEIGHTS), settings_data.get("icp_weights", {}))
    criteria = _deep_merge(dict(DEFAULT_ICP), settings_data.get("icp_criteria", {}))

    return ICPConfigResponse(weights=weights, criteria=criteria)


@router.put("/config/icp", response_model=ICPConfigResponse)
async def update_icp_config(
    body: ICPConfigUpdateRequest,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Update ICP weights and/or criteria. Weights must sum to approximately 1.0."""
    log.info("admin.update_icp_config", workspace_id=workspace_id)

    if body.weights is not None:
        weight_sum = sum(body.weights.values())
        if abs(weight_sum - 1.0) > 0.05:
            raise HTTPException(
                status_code=422,
                detail=f"ICP weights must sum to ~1.0 (got {weight_sum:.3f})",
            )

    settings_data = await _get_settings_data(session, workspace_id)

    if body.weights is not None:
        settings_data["icp_weights"] = body.weights
    if body.criteria is not None:
        settings_data["icp_criteria"] = body.criteria

    await _save_settings_data(session, workspace_id, settings_data)

    # Return merged result
    weights = _deep_merge(dict(ICP_WEIGHTS), settings_data.get("icp_weights", {}))
    criteria = _deep_merge(dict(DEFAULT_ICP), settings_data.get("icp_criteria", {}))

    return ICPConfigResponse(weights=weights, criteria=criteria)


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


@router.get("/config/thresholds", response_model=ThresholdsResponse)
async def get_thresholds(
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Return action thresholds, confidence levels, and signal decay config."""
    log.info("admin.get_thresholds", workspace_id=workspace_id)
    settings_data = await _get_settings_data(session, workspace_id)

    action = _deep_merge(dict(ACTION_THRESHOLDS), settings_data.get("action_thresholds", {}))
    confidence = _deep_merge(dict(CONFIDENCE_LEVELS), settings_data.get("confidence_levels", {}))
    decay = _deep_merge(dict(SIGNAL_DECAY), settings_data.get("signal_decay", {}))

    return ThresholdsResponse(
        action_thresholds=action,
        confidence_levels=confidence,
        signal_decay=decay,
    )


@router.put("/config/thresholds", response_model=ThresholdsResponse)
async def update_thresholds(
    body: ThresholdsUpdateRequest,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Update action thresholds, confidence levels, and/or signal decay."""
    log.info("admin.update_thresholds", workspace_id=workspace_id)
    settings_data = await _get_settings_data(session, workspace_id)

    if body.action_thresholds is not None:
        settings_data["action_thresholds"] = body.action_thresholds
    if body.confidence_levels is not None:
        settings_data["confidence_levels"] = body.confidence_levels
    if body.signal_decay is not None:
        settings_data["signal_decay"] = body.signal_decay

    await _save_settings_data(session, workspace_id, settings_data)

    action = _deep_merge(dict(ACTION_THRESHOLDS), settings_data.get("action_thresholds", {}))
    confidence = _deep_merge(dict(CONFIDENCE_LEVELS), settings_data.get("confidence_levels", {}))
    decay = _deep_merge(dict(SIGNAL_DECAY), settings_data.get("signal_decay", {}))

    return ThresholdsResponse(
        action_thresholds=action,
        confidence_levels=confidence,
        signal_decay=decay,
    )


# ---------------------------------------------------------------------------
# Automation
# ---------------------------------------------------------------------------


@router.get("/config/automation", response_model=AutomationConfigResponse)
async def get_automation_config(
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Return automation config (send caps, kill switch, blocklist)."""
    log.info("admin.get_automation_config", workspace_id=workspace_id)
    settings_data = await _get_settings_data(session, workspace_id)

    return AutomationConfigResponse(
        defaults=_deep_merge(dict(AUTOMATION_DEFAULTS), settings_data.get("automation_defaults", {})),
        auto_outbound_thresholds=_deep_merge(
            dict(AUTO_OUTBOUND_THRESHOLDS),
            settings_data.get("auto_outbound_thresholds", {}),
        ),
        send_caps=_deep_merge(dict(SEND_CAPS), settings_data.get("send_caps", {})),
        blocklist=_deep_merge(dict(BLOCKLIST_CONFIG), settings_data.get("blocklist", {})),
        kill_switch=_deep_merge(dict(KILL_SWITCH), settings_data.get("kill_switch", {})),
        rollback=_deep_merge(dict(ROLLBACK_CONFIG), settings_data.get("rollback", {})),
    )


@router.put("/config/automation", response_model=AutomationConfigResponse)
async def update_automation_config(
    body: AutomationConfigUpdateRequest,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Update automation config."""
    log.info("admin.update_automation_config", workspace_id=workspace_id)
    settings_data = await _get_settings_data(session, workspace_id)

    if body.defaults is not None:
        settings_data["automation_defaults"] = body.defaults
    if body.auto_outbound_thresholds is not None:
        settings_data["auto_outbound_thresholds"] = body.auto_outbound_thresholds
    if body.send_caps is not None:
        settings_data["send_caps"] = body.send_caps
    if body.blocklist is not None:
        settings_data["blocklist"] = body.blocklist
    if body.kill_switch is not None:
        settings_data["kill_switch"] = body.kill_switch

    await _save_settings_data(session, workspace_id, settings_data)

    return AutomationConfigResponse(
        defaults=_deep_merge(dict(AUTOMATION_DEFAULTS), settings_data.get("automation_defaults", {})),
        auto_outbound_thresholds=_deep_merge(
            dict(AUTO_OUTBOUND_THRESHOLDS),
            settings_data.get("auto_outbound_thresholds", {}),
        ),
        send_caps=_deep_merge(dict(SEND_CAPS), settings_data.get("send_caps", {})),
        blocklist=_deep_merge(dict(BLOCKLIST_CONFIG), settings_data.get("blocklist", {})),
        kill_switch=_deep_merge(dict(KILL_SWITCH), settings_data.get("kill_switch", {})),
        rollback=_deep_merge(dict(ROLLBACK_CONFIG), settings_data.get("rollback", {})),
    )


# ---------------------------------------------------------------------------
# Dashboard Stats
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Return dashboard statistics for the workspace."""
    log.info("admin.get_stats", workspace_id=workspace_id)

    # Total accounts scored
    total_result = await session.execute(
        select(func.count(AccountScoreRecord.id)).where(
            AccountScoreRecord.workspace_id == workspace_id
        )
    )
    total_accounts_scored = total_result.scalar() or 0

    # Average scores
    avg_result = await session.execute(
        select(
            func.avg(AccountScoreRecord.overall_priority_score),
            func.avg(AccountScoreRecord.confidence_score),
        ).where(AccountScoreRecord.workspace_id == workspace_id)
    )
    avg_row = avg_result.one()
    average_overall_score = round(float(avg_row[0] or 0), 1)
    average_confidence = round(float(avg_row[1] or 0), 2)

    # Action distribution from briefs
    action_result = await session.execute(
        select(
            SellerBriefRecord.action_type,
            func.count(SellerBriefRecord.id),
        )
        .where(SellerBriefRecord.workspace_id == workspace_id)
        .group_by(SellerBriefRecord.action_type)
    )
    action_distribution = {row[0]: row[1] for row in action_result.all()}

    # Recent briefs count
    briefs_count_result = await session.execute(
        select(func.count(SellerBriefRecord.id)).where(
            SellerBriefRecord.workspace_id == workspace_id
        )
    )
    recent_briefs_count = briefs_count_result.scalar() or 0

    # Feedback summary
    feedback_result = await session.execute(
        select(
            FeedbackEventRecord.action_taken,
            func.count(FeedbackEventRecord.id),
        )
        .where(FeedbackEventRecord.workspace_id == workspace_id)
        .group_by(FeedbackEventRecord.action_taken)
    )
    feedback_summary = {row[0]: row[1] for row in feedback_result.all()}

    return DashboardStatsResponse(
        total_accounts_scored=total_accounts_scored,
        action_distribution=action_distribution,
        average_overall_score=average_overall_score,
        average_confidence=average_confidence,
        recent_briefs_count=recent_briefs_count,
        feedback_summary=feedback_summary,
    )


# ---------------------------------------------------------------------------
# Briefs
# ---------------------------------------------------------------------------


@router.get("/briefs/recent", response_model=list[BriefSummary])
async def list_recent_briefs(
    session: SessionDep,
    workspace_id: WorkspaceDep,
    limit: int = 50,
):
    """List recent briefs with scores and actions."""
    log.info("admin.list_recent_briefs", workspace_id=workspace_id)

    result = await session.execute(
        select(SellerBriefRecord)
        .where(SellerBriefRecord.workspace_id == workspace_id)
        .order_by(SellerBriefRecord.generated_at.desc())
        .limit(limit)
    )
    briefs = result.scalars().all()

    return [
        BriefSummary(
            brief_id=b.id,
            account_id=b.account_id,
            action_type=b.action_type,
            overall_score=b.overall_score,
            confidence_score=b.confidence_score,
            version=b.version,
            generated_at=str(b.generated_at),
        )
        for b in briefs
    ]


# ---------------------------------------------------------------------------
# Knowledge Base
# ---------------------------------------------------------------------------


@router.get("/knowledge", response_model=list[KBFileInfo])
async def list_knowledge_files(
    workspace_id: WorkspaceDep,
):
    """List KB files with metadata."""
    log.info("admin.list_knowledge", workspace_id=workspace_id)

    kb_root = Path(__file__).resolve().parent.parent.parent / "knowledge"
    files: list[KBFileInfo] = []

    if kb_root.exists():
        for md_file in sorted(kb_root.rglob("*.md")):
            # Infer type from parent directory or filename
            rel_path = md_file.relative_to(kb_root)
            parts = rel_path.parts
            file_type = parts[0] if len(parts) > 1 else "general"

            files.append(
                KBFileInfo(
                    filename=md_file.name,
                    file_type=file_type,
                    size_bytes=md_file.stat().st_size,
                    path=str(rel_path),
                )
            )

    return files


@router.post("/knowledge/reload", status_code=202)
async def reload_knowledge(
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Trigger KB reload into pgvector."""
    log.info("admin.reload_knowledge", workspace_id=workspace_id)

    from src.knowledge.loader import KnowledgeBaseLoader

    loader = KnowledgeBaseLoader()
    count = await loader.load_all(workspace_id=workspace_id)

    return {"status": "reloaded", "entries_loaded": count}
