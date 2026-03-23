"""Job handlers for OmniGTM qualification and workflow integration.

Registered handlers are called by the BullMQ worker (runner.py).
Each handler receives a job payload and workspace_id.
"""

from __future__ import annotations

import uuid
from typing import Any

from src.agent.qualification_graph import create_qualification_graph
from src.agent.state import (
    ActionType,
    QualificationState,
)
from src.db.clickhouse import ClickHouseClient
from src.logger import log
from src.worker.queues import enqueue_by_event

# ---------------------------------------------------------------------------
# Shared ClickHouse client (lazy singleton)
# ---------------------------------------------------------------------------

_ch_client: ClickHouseClient | None = None


def _get_ch_client() -> ClickHouseClient:
    global _ch_client
    if _ch_client is None:
        _ch_client = ClickHouseClient()
    return _ch_client


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_qualification_batch(
    payload: dict[str, Any],
    workspace_id: str,
) -> None:
    """Run the qualification graph for a batch of accounts.

    Pulls account_ids and campaign_id from payload, builds a
    QualificationState, runs the graph, and logs results to ClickHouse.

    When accounts were uploaded directly (no CRM), fetches full account data
    from DB so the data_ingester can skip CRM calls.
    """
    account_ids: list[str] = payload.get("account_ids", [])
    campaign_id: str = payload.get("campaign_id", "")

    log.info(
        "handler.qualification_batch.start",
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        account_count=len(account_ids),
    )

    thread_id = f"qual-{workspace_id}-{campaign_id}-{uuid.uuid4().hex[:8]}"

    # Try to fetch full account data from DB (uploaded accounts)
    # If found, pass complete dicts so data_ingester skips CRM
    raw_accounts: list[dict] = []
    if campaign_id:
        try:
            from src.db.queries import async_session_factory, get_campaign_accounts
            async with async_session_factory() as session:
                uploaded = await get_campaign_accounts(
                    session=session,
                    campaign_id=campaign_id,
                    workspace_id=workspace_id,
                )
                if uploaded:
                    raw_accounts = uploaded
                    log.info(
                        "handler.qualification_batch.loaded_uploaded_accounts",
                        workspace_id=workspace_id,
                        campaign_id=campaign_id,
                        count=len(uploaded),
                    )
        except Exception as exc:
            log.warning(
                "handler.qualification_batch.uploaded_account_fetch_failed",
                workspace_id=workspace_id,
                campaign_id=campaign_id,
                error=str(exc),
            )

    # Fall back to ID-only mode if no uploaded accounts found
    if not raw_accounts:
        raw_accounts = [{"id": aid} for aid in account_ids]

    initial_state: QualificationState = {
        "thread_id": thread_id,
        "workspace_id": workspace_id,
        "raw_accounts": raw_accounts,
    }

    graph = await create_qualification_graph()
    config = {"configurable": {"thread_id": thread_id}}

    final_state: dict[str, Any] = {}
    async for event in graph.astream(initial_state, config=config):
        for node_name, node_output in event.items():
            if node_name == "__end__":
                continue
            if isinstance(node_output, dict):
                final_state.update(node_output)

    # Log qualification results to ClickHouse
    ch = _get_ch_client()
    score = final_state.get("account_score")
    recommendation = final_state.get("action_recommendation")
    brief = final_state.get("seller_brief")

    if score and recommendation:
        await ch.log_qualification_event(
            workspace_id=workspace_id,
            account_id=score.account_id,
            event_type="qualification_complete",
            icp_fit_score=score.icp_fit_score,
            pain_fit_score=score.pain_fit_score,
            timing_score=score.timing_score,
            overall_priority_score=score.overall_priority_score,
            action_type=recommendation.action.value,
            confidence_score=recommendation.confidence_score,
            scoring_version=score.scoring_version,
        )

    if brief and recommendation:
        await ch.log_recommendation_event(
            workspace_id=workspace_id,
            account_id=brief.account_id,
            brief_id=brief.id,
            action_type=recommendation.action.value,
            overall_score=score.overall_priority_score if score else 0,
            confidence_score=recommendation.confidence_score,
            contact_count=len(brief.recommended_contacts),
            pain_count=len(brief.likely_pain_points),
            signal_count=len(brief.signals_used),
            model_version=brief.model_version,
            prompt_version=brief.prompt_version,
        )

    log.info(
        "handler.qualification_batch.complete",
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        thread_id=thread_id,
    )


async def handle_brief_to_outbound(
    payload: dict[str, Any],
    workspace_id: str,
) -> None:
    """Convert an approved brief into an outbound campaign execution.

    Loads the brief from PostgreSQL. If action is pursue_now and
    approval_status is approved or auto_approved, creates an OutboundState
    from the brief's recommended contacts and triggers the outbound graph.
    """
    brief_id: str = payload.get("brief_id", "")

    log.info(
        "handler.brief_to_outbound.start",
        workspace_id=workspace_id,
        brief_id=brief_id,
    )

    # Load brief from PostgreSQL via queries.py
    from src.db.queries import get_seller_brief_by_id

    brief_record = await get_seller_brief_by_id(
        brief_id=brief_id,
        workspace_id=workspace_id,
    )

    if not brief_record:
        log.warning(
            "handler.brief_to_outbound.brief_not_found",
            workspace_id=workspace_id,
            brief_id=brief_id,
        )
        return

    action_type = brief_record.get("action_type", "")
    approval_status = brief_record.get("approval_status", "")

    if action_type != ActionType.PURSUE_NOW.value:
        log.info(
            "handler.brief_to_outbound.skipped",
            workspace_id=workspace_id,
            brief_id=brief_id,
            reason=f"action_type is {action_type}, not pursue_now",
        )
        return

    if approval_status not in ("approved", "auto_approved"):
        log.info(
            "handler.brief_to_outbound.skipped",
            workspace_id=workspace_id,
            brief_id=brief_id,
            reason=f"approval_status is {approval_status}",
        )
        return

    # Trigger outbound graph with recommended contacts
    from src.agent.graph import create_outbound_graph

    thread_id = f"outbound-{workspace_id}-{brief_id}-{uuid.uuid4().hex[:8]}"

    outbound_state = {
        "thread_id": thread_id,
        "workspace_id": workspace_id,
        "contacts": brief_record.get("recommended_contacts", []),
        "current_stage": 0,
        "max_stages": 3,
        "should_continue": True,
    }

    graph = await create_outbound_graph()
    config = {"configurable": {"thread_id": thread_id}}

    async for event in graph.astream(outbound_state, config=config):
        pass  # Let the graph run to completion

    # Log the handoff
    ch = _get_ch_client()
    await ch.log_session_event(
        workspace_id=workspace_id,
        session_id=thread_id,
        event_type="brief_to_outbound_handoff",
        metadata={
            "brief_id": brief_id,
            "action_type": action_type,
        },
    )

    log.info(
        "handler.brief_to_outbound.complete",
        workspace_id=workspace_id,
        brief_id=brief_id,
        thread_id=thread_id,
    )


async def handle_daily_rescore(
    payload: dict[str, Any],
    workspace_id: str,
) -> None:
    """Run daily re-scoring for all active accounts in the workspace."""
    log.info("handler.daily_rescore.start", workspace_id=workspace_id)

    from src.worker.scheduler import schedule_daily_rescore

    job_id = await schedule_daily_rescore(workspace_id)

    log.info(
        "handler.daily_rescore.complete",
        workspace_id=workspace_id,
        enqueued_job_id=job_id,
    )


async def handle_signal_refresh(
    payload: dict[str, Any],
    workspace_id: str,
) -> None:
    """Re-run signal detection on all scored accounts in the workspace."""
    log.info("handler.signal_refresh.start", workspace_id=workspace_id)

    from src.worker.scheduler import schedule_signal_refresh

    job_id = await schedule_signal_refresh(workspace_id)

    log.info(
        "handler.signal_refresh.complete",
        workspace_id=workspace_id,
        enqueued_job_id=job_id,
    )


async def handle_brief_refresh(
    payload: dict[str, Any],
    workspace_id: str,
) -> None:
    """Re-generate stale seller briefs in the workspace."""
    log.info("handler.brief_refresh.start", workspace_id=workspace_id)

    from src.worker.scheduler import schedule_brief_refresh

    max_age_days = payload.get("max_age_days", 7)
    job_id = await schedule_brief_refresh(workspace_id, max_age_days=max_age_days)

    log.info(
        "handler.brief_refresh.complete",
        workspace_id=workspace_id,
        enqueued_job_id=job_id,
    )


async def handle_brief_approval(
    payload: dict[str, Any],
    workspace_id: str,
) -> None:
    """Process a brief approval or rejection from a reviewer.

    If approved, enqueues a brief_to_outbound job to continue the pipeline.
    If rejected, logs the rejection — no further action.
    """
    thread_id: str = payload.get("thread_id", "")
    approved: bool = payload.get("approved", False)
    reviewer: str = payload.get("reviewer", "unknown")

    log.info(
        "handler.brief_approval.start",
        workspace_id=workspace_id,
        thread_id=thread_id,
        approved=approved,
        reviewer=reviewer,
    )

    if approved:
        # Extract brief_id from thread_id or payload
        brief_id: str = payload.get("brief_id", thread_id)

        job_id = await enqueue_by_event(
            event_type="brief_to_outbound",
            payload={
                "brief_id": brief_id,
            },
            workspace_id=workspace_id,
        )

        log.info(
            "handler.brief_approval.approved",
            workspace_id=workspace_id,
            thread_id=thread_id,
            reviewer=reviewer,
            enqueued_job_id=job_id,
        )
    else:
        # Log rejection — no further action
        ch = _get_ch_client()
        await ch.log_session_event(
            workspace_id=workspace_id,
            session_id=thread_id,
            event_type="brief_rejected",
            metadata={
                "reviewer": reviewer,
                "thread_id": thread_id,
            },
        )

        log.info(
            "handler.brief_approval.rejected",
            workspace_id=workspace_id,
            thread_id=thread_id,
            reviewer=reviewer,
        )


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

HANDLER_REGISTRY: dict[str, Any] = {
    "qualification_batch": handle_qualification_batch,
    "brief_to_outbound": handle_brief_to_outbound,
    "brief_approval": handle_brief_approval,
    "daily_rescore": handle_daily_rescore,
    "signal_refresh": handle_signal_refresh,
    "brief_refresh": handle_brief_refresh,
}
