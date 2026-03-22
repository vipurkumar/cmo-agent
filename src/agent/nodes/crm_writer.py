"""CRM writeback node — persists qualification results to HubSpot.

Writes:
- Account score as custom properties on the HubSpot company
- Seller brief as a note/engagement on the HubSpot company
- Action recommendation as a custom property

Also persists to PostgreSQL via save_seller_brief and save_account_score.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.agent.state import QualificationState
from src.db.queries import async_session_factory, save_account_score, save_seller_brief
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
        raise RuntimeError("crm_writer tools not initialised — call init_tools() first")
    return HubSpotTool(_rate_limiter)


async def crm_writer(state: QualificationState) -> dict:
    """Write qualification results to HubSpot CRM and PostgreSQL."""
    thread_id = state["thread_id"]
    account = state.get("current_account")
    if account is None:
        return {}

    workspace_id = account.workspace_id
    log.info("crm_writer.start", thread_id=thread_id, workspace_id=workspace_id)

    account_score = state.get("account_score")
    seller_brief = state.get("seller_brief")
    action_recommendation = state.get("action_recommendation")
    plan_name = "pro"

    hubspot_tool = _get_hubspot()

    # ── 1. Write account score to HubSpot company ────────────────────────
    if account_score:
        hubspot_properties: dict[str, str | int | float] = {
            "omnigtm_fit_score": account_score.icp_fit_score,
            "omnigtm_pain_score": account_score.pain_fit_score,
            "omnigtm_timing_score": account_score.timing_score,
            "omnigtm_priority_score": account_score.overall_priority_score,
            "omnigtm_confidence": account_score.confidence_score,
            "omnigtm_last_scored": datetime.now(timezone.utc).isoformat(),
        }

        if action_recommendation:
            hubspot_properties["omnigtm_action"] = action_recommendation.action.value

        # Use account.id as the HubSpot company record_id (stored in metadata
        # if available, otherwise fall back to account.id).
        hubspot_company_id = account.metadata.get("hubspot_company_id", account.id)

        try:
            await hubspot_tool.run(
                operation="update",
                workspace_id=workspace_id,
                plan=plan_name,
                object_type="companies",
                record_id=hubspot_company_id,
                properties=hubspot_properties,
            )
            log.info(
                "crm_writer.hubspot_score_written",
                thread_id=thread_id,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            log.error(
                "crm_writer.hubspot_score_error",
                thread_id=thread_id,
                workspace_id=workspace_id,
                error=str(exc),
            )

    # ── 2. Create engagement note with brief summary ─────────────────────
    if seller_brief:
        note_body = (
            f"OmniGTM Seller Brief — {account.company_name}\n\n"
            f"Snapshot: {seller_brief.account_snapshot}\n\n"
            f"Why Now: {seller_brief.why_now}\n\n"
            f"Action: {seller_brief.recommended_action.action.value}\n"
            f"Confidence: {seller_brief.recommended_action.confidence_score}\n"
        )

        hubspot_company_id = account.metadata.get("hubspot_company_id", account.id)

        try:
            await hubspot_tool.run(
                operation="log_activity",
                workspace_id=workspace_id,
                plan=plan_name,
                object_type="engagements",
                properties={
                    "hs_engagement_type": "NOTE",
                    "hs_note_body": note_body,
                    "hs_company_id": hubspot_company_id,
                },
            )
            log.info(
                "crm_writer.hubspot_note_created",
                thread_id=thread_id,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            log.error(
                "crm_writer.hubspot_note_error",
                thread_id=thread_id,
                workspace_id=workspace_id,
                error=str(exc),
            )

    # ── 3. Persist to PostgreSQL ─────────────────────────────────────────
    try:
        async with async_session_factory() as session, session.begin():
            if account_score:
                await save_account_score(
                    session=session,
                    workspace_id=workspace_id,
                    account_id=account.id,
                    icp_fit_score=account_score.icp_fit_score,
                    pain_fit_score=account_score.pain_fit_score,
                    timing_score=account_score.timing_score,
                    overall_priority_score=account_score.overall_priority_score,
                    confidence_score=account_score.confidence_score,
                    fit_reasons=[e.model_dump() for e in account_score.fit_reasons],
                    non_fit_reasons=[e.model_dump() for e in account_score.non_fit_reasons],
                    is_disqualified=account_score.is_disqualified,
                    disqualify_reason=account_score.disqualify_reason,
                )

            if seller_brief:
                await save_seller_brief(
                    session=session,
                    workspace_id=workspace_id,
                    account_id=account.id,
                    brief_json=seller_brief.model_dump(mode="json"),
                    action_type=seller_brief.recommended_action.action.value,
                    overall_score=(
                        account_score.overall_priority_score if account_score else 0
                    ),
                    confidence_score=(
                        seller_brief.recommended_action.confidence_score
                    ),
                    version=seller_brief.version,
                )

        log.info(
            "crm_writer.postgres_saved",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
    except Exception as exc:
        log.error(
            "crm_writer.postgres_error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )

    log.info("crm_writer.complete", thread_id=thread_id, workspace_id=workspace_id)
    return {}
