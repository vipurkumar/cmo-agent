"""Auto-outbound gate — narrow automation for high-confidence cases.

Only auto-triggers outbound when ALL of these are true:
1. Automation is enabled for the workspace
2. Kill switch is not active
3. Account is not blocklisted
4. Send caps are not exceeded
5. Brief meets strict auto-outbound thresholds (higher than manual pursue_now)
6. Action is pursue_now with high confidence

If any check fails, the brief stays in the manual queue.
"""

from __future__ import annotations

from redis.asyncio import Redis

from src.agent.state import ActionType, QualificationState
from src.config import settings
from src.config.automation import AUTOMATION_DEFAULTS, AUTO_OUTBOUND_THRESHOLDS
from src.db.clickhouse import ClickHouseClient
from src.guardrails.blocklist import BlocklistEnforcer
from src.guardrails.kill_switch import KillSwitch
from src.guardrails.send_caps import SendCapEnforcer, SendCapError
from src.logger import log
from src.worker.queues import enqueue_by_event

# ---------------------------------------------------------------------------
# Module-level lazy-init Redis client and guardrails
# ---------------------------------------------------------------------------

_redis: Redis | None = None
_kill_switch: KillSwitch | None = None
_blocklist: BlocklistEnforcer | None = None
_send_caps: SendCapEnforcer | None = None
_clickhouse: ClickHouseClient | None = None


def init_guardrails(redis_client: Redis, clickhouse: ClickHouseClient | None = None) -> None:
    """Inject the shared Redis client (called once at app startup)."""
    global _redis, _kill_switch, _blocklist, _send_caps, _clickhouse
    _redis = redis_client
    _kill_switch = KillSwitch(redis_client)
    _blocklist = BlocklistEnforcer(redis_client)
    _send_caps = SendCapEnforcer(redis_client)
    _clickhouse = clickhouse


def _get_guardrails() -> tuple[KillSwitch, BlocklistEnforcer, SendCapEnforcer]:
    if _kill_switch is None or _blocklist is None or _send_caps is None:
        raise RuntimeError(
            "auto_outbound_gate guardrails not initialised — call init_guardrails() first"
        )
    return _kill_switch, _blocklist, _send_caps


def _is_automation_enabled(state: QualificationState) -> bool:
    """Check if automation is enabled for the workspace.

    Checks campaign-level settings first, then falls back to defaults.
    """
    campaign = state.get("campaign")
    if campaign and campaign.sequence_config:
        automation_cfg = campaign.sequence_config.get("automation", {})
        if "enabled" in automation_cfg:
            return bool(automation_cfg["enabled"])
    return bool(AUTOMATION_DEFAULTS.get("enabled", False))


def _brief_meets_thresholds(state: QualificationState) -> tuple[bool, str]:
    """Validate the brief against strict auto-outbound thresholds.

    Returns (passes, reason_if_failed).
    """
    thresholds = AUTO_OUTBOUND_THRESHOLDS

    # Overall priority score
    account_score = state.get("account_score")
    if not account_score:
        return False, "no_account_score"
    if account_score.overall_priority_score < thresholds["overall_priority_min"]:
        return False, (
            f"overall_priority_score={account_score.overall_priority_score} "
            f"< threshold={thresholds['overall_priority_min']}"
        )

    # Account score confidence
    if account_score.confidence_score < thresholds["account_score_confidence_min"]:
        return False, (
            f"account_score_confidence={account_score.confidence_score} "
            f"< threshold={thresholds['account_score_confidence_min']}"
        )

    # Top contact relevance
    ranked_contacts = state.get("ranked_contacts", [])
    if not ranked_contacts:
        return False, "no_ranked_contacts"
    top_relevance = ranked_contacts[0].relevance_score
    if top_relevance < thresholds["top_contact_relevance_min"]:
        return False, (
            f"top_contact_relevance={top_relevance} "
            f"< threshold={thresholds['top_contact_relevance_min']}"
        )

    # Pain confidence — use max across hypotheses
    pain_hypotheses = state.get("pain_hypotheses", [])
    if len(pain_hypotheses) < thresholds["min_pain_hypotheses"]:
        return False, (
            f"pain_hypotheses_count={len(pain_hypotheses)} "
            f"< threshold={thresholds['min_pain_hypotheses']}"
        )
    max_pain_confidence = max(
        (ph.confidence_score for ph in pain_hypotheses), default=0.0
    )
    if max_pain_confidence < thresholds["pain_confidence_min"]:
        return False, (
            f"pain_confidence={max_pain_confidence} "
            f"< threshold={thresholds['pain_confidence_min']}"
        )

    # Signal count
    signals = state.get("signals", [])
    if len(signals) < thresholds["min_signals"]:
        return False, (
            f"signal_count={len(signals)} "
            f"< threshold={thresholds['min_signals']}"
        )

    # Unknowns count from the seller brief
    seller_brief = state.get("seller_brief")
    unknowns_count = len(seller_brief.risks_and_unknowns) if seller_brief else 0
    if unknowns_count > thresholds["max_unknowns"]:
        return False, (
            f"unknowns_count={unknowns_count} "
            f"> threshold={thresholds['max_unknowns']}"
        )

    return True, ""


async def _log_decision(
    workspace_id: str,
    account_id: str,
    triggered: bool,
    reason: str,
    state: QualificationState,
) -> None:
    """Log the auto-outbound decision to ClickHouse (best effort)."""
    if _clickhouse is None:
        return
    try:
        account_score = state.get("account_score")
        await _clickhouse.log_qualification_event(
            workspace_id=workspace_id,
            account_id=account_id,
            event_type="auto_outbound_decision",
            overall_priority_score=(
                account_score.overall_priority_score if account_score else 0
            ),
            action_type="pursue_now" if triggered else "manual_queue",
            confidence_score=(
                account_score.confidence_score if account_score else 0.0
            ),
            metadata={
                "auto_triggered": triggered,
                "reason": reason,
            },
        )
    except Exception as exc:
        log.error(
            "auto_outbound_gate.clickhouse_error",
            workspace_id=workspace_id,
            account_id=account_id,
            error=str(exc),
        )


async def auto_outbound_gate(state: QualificationState) -> dict:
    """Decide whether to auto-trigger outbound for high-confidence cases.

    Runs a series of guardrail checks in order. If ALL pass, enqueues a
    ``brief_to_outbound`` job. Otherwise, the brief stays in the manual queue.
    """
    thread_id = state.get("thread_id", "")
    workspace_id = state.get("workspace_id", "")
    account = state.get("current_account")
    account_id = account.id if account else ""

    log.info(
        "auto_outbound_gate.start",
        thread_id=thread_id,
        workspace_id=workspace_id,
        account_id=account_id,
    )

    kill_switch, blocklist, send_caps = _get_guardrails()

    # --- Check 1: Is automation enabled? ---
    try:
        if not _is_automation_enabled(state):
            reason = "automation_disabled"
            log.info(
                "auto_outbound_gate.skip",
                thread_id=thread_id,
                workspace_id=workspace_id,
                reason=reason,
            )
            await _log_decision(workspace_id, account_id, False, reason, state)
            return {
                "auto_outbound_triggered": False,
                "auto_outbound_skip_reason": reason,
            }
    except Exception as exc:
        reason = f"automation_check_error: {exc}"
        log.error(
            "auto_outbound_gate.automation_check_error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        await _log_decision(workspace_id, account_id, False, reason, state)
        return {
            "auto_outbound_triggered": False,
            "auto_outbound_skip_reason": reason,
        }

    # --- Check 2: Is kill switch active? ---
    try:
        is_paused, pause_reason = await kill_switch.is_paused(workspace_id)
        if is_paused:
            reason = f"kill_switch_active: {pause_reason}"
            log.info(
                "auto_outbound_gate.skip",
                thread_id=thread_id,
                workspace_id=workspace_id,
                reason=reason,
            )
            await _log_decision(workspace_id, account_id, False, reason, state)
            return {
                "auto_outbound_triggered": False,
                "auto_outbound_skip_reason": reason,
            }
    except Exception as exc:
        reason = f"kill_switch_check_error: {exc}"
        log.error(
            "auto_outbound_gate.kill_switch_error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        await _log_decision(workspace_id, account_id, False, reason, state)
        return {
            "auto_outbound_triggered": False,
            "auto_outbound_skip_reason": reason,
        }

    # --- Check 3: Is action pursue_now? ---
    recommendation = state.get("action_recommendation")
    if not recommendation or recommendation.action != ActionType.PURSUE_NOW:
        action_label = recommendation.action.value if recommendation else "none"
        reason = f"action_not_pursue_now: {action_label}"
        log.info(
            "auto_outbound_gate.skip",
            thread_id=thread_id,
            workspace_id=workspace_id,
            reason=reason,
        )
        await _log_decision(workspace_id, account_id, False, reason, state)
        return {
            "auto_outbound_triggered": False,
            "auto_outbound_skip_reason": reason,
        }

    # --- Check 4: Does brief meet auto-outbound thresholds? ---
    try:
        meets_thresholds, threshold_reason = _brief_meets_thresholds(state)
        if not meets_thresholds:
            reason = f"threshold_not_met: {threshold_reason}"
            log.info(
                "auto_outbound_gate.skip",
                thread_id=thread_id,
                workspace_id=workspace_id,
                reason=reason,
            )
            await _log_decision(workspace_id, account_id, False, reason, state)
            return {
                "auto_outbound_triggered": False,
                "auto_outbound_skip_reason": reason,
            }
    except Exception as exc:
        reason = f"threshold_check_error: {exc}"
        log.error(
            "auto_outbound_gate.threshold_error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        await _log_decision(workspace_id, account_id, False, reason, state)
        return {
            "auto_outbound_triggered": False,
            "auto_outbound_skip_reason": reason,
        }

    # --- Check 5: Is target blocklisted? ---
    try:
        contact_email = None
        ranked_contacts = state.get("ranked_contacts", [])
        if ranked_contacts:
            # Get email from the contacts list if available
            contacts = state.get("contacts", [])
            top_contact_id = ranked_contacts[0].contact_id
            for c in contacts:
                if c.id == top_contact_id:
                    contact_email = c.email
                    break

        domain = account.domain if account else None
        company_name = account.company_name if account else None

        is_blocked, block_reason = await blocklist.is_blocked(
            workspace_id=workspace_id,
            email=contact_email,
            domain=domain,
            company_name=company_name,
        )
        if is_blocked:
            reason = f"blocklisted: {block_reason}"
            log.info(
                "auto_outbound_gate.skip",
                thread_id=thread_id,
                workspace_id=workspace_id,
                reason=reason,
            )
            await _log_decision(workspace_id, account_id, False, reason, state)
            return {
                "auto_outbound_triggered": False,
                "auto_outbound_skip_reason": reason,
            }
    except Exception as exc:
        reason = f"blocklist_check_error: {exc}"
        log.error(
            "auto_outbound_gate.blocklist_error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        await _log_decision(workspace_id, account_id, False, reason, state)
        return {
            "auto_outbound_triggered": False,
            "auto_outbound_skip_reason": reason,
        }

    # --- Check 6: Are send caps OK? ---
    try:
        await send_caps.check_and_increment(
            workspace_id=workspace_id,
            account_id=account_id,
        )
    except SendCapError as exc:
        reason = f"send_cap_exceeded: {exc.cap_type} (current={exc.current}, limit={exc.limit})"
        log.info(
            "auto_outbound_gate.skip",
            thread_id=thread_id,
            workspace_id=workspace_id,
            reason=reason,
        )
        await _log_decision(workspace_id, account_id, False, reason, state)
        return {
            "auto_outbound_triggered": False,
            "auto_outbound_skip_reason": reason,
        }
    except Exception as exc:
        reason = f"send_cap_check_error: {exc}"
        log.error(
            "auto_outbound_gate.send_cap_error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        await _log_decision(workspace_id, account_id, False, reason, state)
        return {
            "auto_outbound_triggered": False,
            "auto_outbound_skip_reason": reason,
        }

    # --- All checks passed — enqueue outbound ---
    seller_brief = state.get("seller_brief")
    brief_id = seller_brief.id if seller_brief else ""

    try:
        await enqueue_by_event(
            event_type="brief_to_outbound",
            payload={
                "brief_id": brief_id,
                "account_id": account_id,
                "thread_id": thread_id,
                "auto_triggered": True,
            },
            workspace_id=workspace_id,
        )
    except Exception as exc:
        reason = f"enqueue_error: {exc}"
        log.error(
            "auto_outbound_gate.enqueue_error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        await _log_decision(workspace_id, account_id, False, reason, state)
        return {
            "auto_outbound_triggered": False,
            "auto_outbound_skip_reason": reason,
        }

    log.info(
        "auto_outbound_gate.triggered",
        thread_id=thread_id,
        workspace_id=workspace_id,
        account_id=account_id,
        brief_id=brief_id,
    )
    await _log_decision(workspace_id, account_id, True, "all_checks_passed", state)

    return {"auto_outbound_triggered": True}
