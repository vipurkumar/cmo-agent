"""icp_scorer node — scores the current account on ICP fit, pain fit, and timing.

Combines deterministic ICP scoring, LLM-based pain scoring (via call_claude),
and timing scoring from signals into an overall priority score.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from src.agent.state import AccountScore, Evidence, EvidenceType, QualificationState
from src.config import settings
from src.llm.budget import call_claude
from src.llm.prompts import SYSTEM_PAIN_SCORER
from src.logger import log
from src.scoring.icp_rules import score_icp_fit
from src.scoring.timing_rules import score_timing


async def icp_scorer(state: QualificationState) -> dict:
    """Score the current account on ICP fit, pain fit, and timing."""
    thread_id = state["thread_id"]
    workspace_id = state["workspace_id"]
    account = state.get("current_account")

    if account is None:
        return {"error": "No current_account set"}

    log.info(
        "icp_scorer.start",
        thread_id=thread_id,
        workspace_id=workspace_id,
        account_id=account.id,
    )

    # --- ICP fit score (deterministic) ---
    campaign = state.get("campaign")
    icp_criteria = campaign.icp_criteria if campaign else None

    icp_fit_score, fit_reasons, non_fit_reasons, is_disqualified, dq_reason, icp_confidence = (
        score_icp_fit(account, icp=icp_criteria)
    )

    # Short-circuit if disqualified
    if is_disqualified:
        score = AccountScore(
            account_id=account.id,
            workspace_id=workspace_id,
            icp_fit_score=0,
            pain_fit_score=0,
            timing_score=0,
            overall_priority_score=0,
            fit_reasons=fit_reasons,
            non_fit_reasons=non_fit_reasons,
            confidence_score=icp_confidence,
            is_disqualified=True,
            disqualify_reason=dq_reason,
            scored_at=datetime.now(tz=timezone.utc),
        )
        log.info(
            "icp_scorer.disqualified",
            thread_id=thread_id,
            workspace_id=workspace_id,
            account_id=account.id,
            reason=dq_reason,
        )
        return {"account_score": score}

    # --- Timing score (deterministic, from signals) ---
    signals = state.get("signals") or []
    timing_score, timing_confidence = score_timing(signals)

    # --- Pain fit score (LLM-based) ---
    pain_fit_score = 50  # default fallback
    pain_confidence = 0.3
    pain_evidence: list[Evidence] = []

    try:
        user_prompt = (
            f"## Account\n"
            f"Name: {account.company_name}\n"
            f"Domain: {account.domain or 'N/A'}\n"
            f"Industry: {account.industry or 'N/A'}\n"
            f"Employee Count: {account.employee_count or 'N/A'}\n"
            f"Revenue: {account.revenue or 'N/A'}\n"
            f"Metadata: {json.dumps(account.metadata)}\n\n"
            f"## Signals Detected\n"
            f"{json.dumps([s.model_dump(mode='json') for s in signals[:10]], indent=2, default=str)}\n\n"
            "Score the pain fit for monetization/pricing pain. "
            "Return JSON with keys: pain_fit_score, reasoning, evidence, confidence."
        )

        raw = await call_claude(
            task="account_pain_scoring",
            system=SYSTEM_PAIN_SCORER,
            user=user_prompt,
            workspace_id=workspace_id,
            model=settings.CLAUDE_MODEL,
        )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(
                "icp_scorer.pain_json_parse_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                raw=raw[:200],
            )
            data = {}

        pain_fit_score = int(data.get("pain_fit_score", 50))
        pain_fit_score = max(0, min(100, pain_fit_score))
        pain_confidence = float(data.get("confidence", 0.3))

        # Parse evidence from LLM response
        for ev_data in data.get("evidence", []):
            if isinstance(ev_data, dict):
                pain_evidence.append(Evidence(
                    statement=ev_data.get("statement", ev_data.get("fact", "")),
                    evidence_type=EvidenceType.INFERENCE,
                    source="pain_scorer_llm",
                    confidence=float(ev_data.get("confidence", 0.5)),
                ))

    except Exception as exc:
        log.warning(
            "icp_scorer.pain_scoring_failed",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        # Continue with default pain_fit_score

    # --- Overall priority score (weighted average) ---
    overall_priority_score = int(round(
        icp_fit_score * 0.35 + pain_fit_score * 0.35 + timing_score * 0.30
    ))
    overall_priority_score = max(0, min(100, overall_priority_score))

    # Combined confidence
    combined_confidence = (
        icp_confidence * 0.35 + pain_confidence * 0.35 + timing_confidence * 0.30
    )

    # Merge evidence into fit/non_fit reasons
    for ev in pain_evidence:
        if pain_fit_score >= 50:
            fit_reasons.append(ev)
        else:
            non_fit_reasons.append(ev)

    score = AccountScore(
        account_id=account.id,
        workspace_id=workspace_id,
        icp_fit_score=icp_fit_score,
        pain_fit_score=pain_fit_score,
        timing_score=timing_score,
        overall_priority_score=overall_priority_score,
        fit_reasons=fit_reasons,
        non_fit_reasons=non_fit_reasons,
        confidence_score=round(combined_confidence, 3),
        is_disqualified=False,
        disqualify_reason=None,
        scored_at=datetime.now(tz=timezone.utc),
    )

    log.info(
        "icp_scorer.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        account_id=account.id,
        icp_fit=icp_fit_score,
        pain_fit=pain_fit_score,
        timing=timing_score,
        overall=overall_priority_score,
    )
    return {"account_score": score}
