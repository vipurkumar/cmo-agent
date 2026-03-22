"""Zoho CRM writeback node — persists qualification results to Zoho CRM.

Writes:
- Account score as custom fields on the Zoho Accounts module
- Seller brief as a note on the Zoho account
- Action recommendation as a custom field

Mirrors crm_writer.py but targets Zoho instead of HubSpot.
CRM write failure is logged but does not crash the pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.agent.state import QualificationState
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.zoho_sync import ZohoSyncTool

# ---------------------------------------------------------------------------
# Module-level tool injection (same pattern as researcher.py)
# ---------------------------------------------------------------------------

_zoho_tool: ZohoSyncTool | None = None


def init_tools(rate_limiter: RateLimiter) -> None:
    """Initialize tools — called once at app startup."""
    global _zoho_tool
    _zoho_tool = ZohoSyncTool(rate_limiter)


def _get_zoho_tool() -> ZohoSyncTool:
    if _zoho_tool is None:
        _zoho_tool_fallback = ZohoSyncTool(RateLimiter.__new__(RateLimiter))
        return _zoho_tool_fallback
    return _zoho_tool


# ---------------------------------------------------------------------------
# Zoho field mapping
# ---------------------------------------------------------------------------

ZOHO_SCORE_FIELDS = {
    "OmniGTM_Fit_Score": "icp_fit_score",
    "OmniGTM_Pain_Score": "pain_fit_score",
    "OmniGTM_Timing_Score": "timing_score",
    "OmniGTM_Priority_Score": "overall_priority_score",
    "OmniGTM_Action": "action",
    "OmniGTM_Confidence": "confidence_score",
    "OmniGTM_Last_Scored": "scored_at",
}


async def zoho_writer(state: QualificationState) -> dict:
    """Write qualification results to Zoho CRM."""
    workspace_id = state.get("workspace_id", "")
    account = state.get("current_account")
    score = state.get("account_score")
    brief = state.get("seller_brief")
    action = state.get("action_recommendation")

    log.info(
        "zoho_writer.start",
        workspace_id=workspace_id,
        account_id=account.id if account else None,
    )

    if not account:
        log.warning("zoho_writer.skip", reason="no_current_account")
        return {}

    zoho = _get_zoho_tool()

    # 1. Update account custom fields with scores
    if score:
        try:
            score_data: dict[str, Any] = {
                "OmniGTM_Fit_Score": score.icp_fit_score,
                "OmniGTM_Pain_Score": score.pain_fit_score,
                "OmniGTM_Timing_Score": score.timing_score,
                "OmniGTM_Priority_Score": score.overall_priority_score,
                "OmniGTM_Confidence": round(score.confidence_score, 3),
                "OmniGTM_Last_Scored": datetime.now(UTC).isoformat(),
            }
            if action:
                score_data["OmniGTM_Action"] = action.action.value

            # Upsert by company name / domain
            score_data["Account_Name"] = account.company_name
            if account.domain:
                score_data["Website"] = account.domain

            await zoho.run(
                record_type="Accounts",
                workspace_id=workspace_id,
                plan="pro",
                data=score_data,
                operation="upsert",
            )
            log.info(
                "zoho_writer.scores_written",
                workspace_id=workspace_id,
                account_name=account.company_name,
            )
        except Exception as exc:
            log.error(
                "zoho_writer.score_write_failed",
                error=str(exc),
                workspace_id=workspace_id,
                account_name=account.company_name,
            )

    # 2. Create a note with the brief summary
    if brief:
        try:
            note_title = (
                f"OmniGTM Brief v{brief.version}: "
                f"{action.action.value if action else 'unknown'} "
                f"(score: {score.overall_priority_score if score else 'N/A'})"
            )
            note_body_parts = [
                f"## {note_title}",
                f"\n**Account Snapshot**: {brief.account_snapshot}",
                f"\n**Why This Account**: {brief.why_this_account}",
                f"\n**Why Now**: {brief.why_now}",
                "\n**Pain Points**:",
            ]
            for ph in brief.likely_pain_points[:3]:
                note_body_parts.append(
                    f"- {ph.pain_type.value}: {ph.score}/100 "
                    f"(confidence: {ph.confidence_score:.2f})"
                )

            if brief.recommended_contacts:
                note_body_parts.append("\n**Top Contacts**:")
                for rc in brief.recommended_contacts[:3]:
                    note_body_parts.append(
                        f"- {rc.name} ({rc.title}) — {rc.likely_role.value}, "
                        f"relevance: {rc.relevance_score}"
                    )

            note_body_parts.append(
                f"\n**Risks**: {', '.join(brief.risks_and_unknowns[:3])}"
            )

            note_content = "\n".join(note_body_parts)

            await zoho.run(
                record_type="Notes",
                workspace_id=workspace_id,
                plan="pro",
                data={
                    "Note_Title": note_title,
                    "Note_Content": note_content,
                    "Parent_Id": account.id,
                    "se_module": "Accounts",
                },
                operation="create",
            )
            log.info(
                "zoho_writer.brief_note_created",
                workspace_id=workspace_id,
                account_name=account.company_name,
            )
        except Exception as exc:
            log.error(
                "zoho_writer.brief_note_failed",
                error=str(exc),
                workspace_id=workspace_id,
            )

    # 3. Create a Zoho task for pursue_now / human_review_required
    if action and action.action.value in ("pursue_now", "human_review_required"):
        try:
            contact_name = action.best_first_contact.name if action.best_first_contact else "unknown"
            task_subject = (
                f"OmniGTM: {action.action.value.replace('_', ' ').title()} — "
                f"{account.company_name}"
            )
            task_description = (
                f"Action: {action.explanation}\n\n"
                f"Best contact: {contact_name}\n"
                f"Channel: {action.best_channel or 'email'}\n"
                f"Confidence: {action.confidence_score:.2f}"
            )

            due_days = 2 if action.action.value == "pursue_now" else 5
            due_date = datetime.now(UTC)
            import datetime as dt_module
            due_date = due_date + dt_module.timedelta(days=due_days)

            await zoho.run(
                record_type="Tasks",
                workspace_id=workspace_id,
                plan="pro",
                data={
                    "Subject": task_subject,
                    "Description": task_description,
                    "Due_Date": due_date.strftime("%Y-%m-%d"),
                    "Priority": "High" if action.action.value == "pursue_now" else "Normal",
                    "Status": "Not Started",
                    "What_Id": account.id,
                    "se_module": "Accounts",
                },
                operation="create",
            )
            log.info(
                "zoho_writer.task_created",
                workspace_id=workspace_id,
                action=action.action.value,
                account_name=account.company_name,
            )
        except Exception as exc:
            log.error(
                "zoho_writer.task_create_failed",
                error=str(exc),
                workspace_id=workspace_id,
            )

    log.info(
        "zoho_writer.complete",
        workspace_id=workspace_id,
        account_name=account.company_name if account else None,
    )
    return {}
