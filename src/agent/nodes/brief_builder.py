"""brief_builder node — assembles a comprehensive seller brief from all upstream data.

Uses call_claude() with SYSTEM_BRIEF_BUILDER to synthesize account score,
buying committee, signals, pain hypotheses, value props, and action
recommendation into a skimmable SellerBrief.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from src.agent.state import (
    ActionRecommendation,
    ActionType,
    PainHypothesis,
    QualificationState,
    RankedContact,
    SellerBrief,
    ValuePropRecommendation,
)
from src.config import settings
from src.llm.budget import call_claude
from src.llm.prompts import SYSTEM_BRIEF_BUILDER
from src.logger import log


async def brief_builder(state: QualificationState) -> dict:
    """Build a comprehensive seller brief from all upstream intelligence."""
    thread_id = state["thread_id"]
    account = state.get("current_account")
    if account is None:
        return {"error": "No current_account set"}

    workspace_id = account.workspace_id
    log.info("brief_builder.start", thread_id=thread_id, workspace_id=workspace_id)

    account_score = state.get("account_score")
    buying_committee = state.get("buying_committee")
    signals = state.get("signals", [])
    pain_hypotheses = state.get("pain_hypotheses", [])
    value_props = state.get("value_props", [])
    action_recommendation = state.get("action_recommendation")
    ranked_contacts = state.get("ranked_contacts", [])
    enrichment = state.get("enrichment")

    # Build comprehensive context for the LLM
    context_parts = [
        "## Account",
        f"Name: {account.company_name}",
        f"Domain: {account.domain or 'N/A'}",
        f"Industry: {account.industry or 'N/A'}",
        f"Employee Count: {account.employee_count or 'N/A'}",
        f"Revenue: {account.revenue or 'N/A'}",
    ]

    # Account score
    if account_score:
        context_parts.append("\n## Account Score")
        context_parts.append(f"ICP Fit: {account_score.icp_fit_score}/100")
        context_parts.append(f"Pain Fit: {account_score.pain_fit_score}/100")
        context_parts.append(f"Timing: {account_score.timing_score}/100")
        context_parts.append(f"Overall Priority: {account_score.overall_priority_score}/100")
        context_parts.append(f"Confidence: {account_score.confidence_score}")
        if account_score.fit_reasons:
            context_parts.append("Fit Reasons:")
            for r in account_score.fit_reasons:
                context_parts.append(f"  - {r.statement} (source: {r.source})")
        if account_score.non_fit_reasons:
            context_parts.append("Non-Fit Reasons:")
            for r in account_score.non_fit_reasons:
                context_parts.append(f"  - {r.statement} (source: {r.source})")

    # Buying committee / ranked contacts
    if ranked_contacts:
        context_parts.append("\n## Buying Committee")
        for rc in ranked_contacts[:5]:
            context_parts.append(
                f"- {rc.name} | {rc.title} | Role: {rc.likely_role.value} | "
                f"Relevance: {rc.relevance_score} | {rc.reason_for_relevance}"
            )

    # Signals
    if signals:
        context_parts.append("\n## Signals")
        for sig in signals:
            date_str = sig.event_date.isoformat() if sig.event_date else "N/A"
            context_parts.append(
                f"- [{sig.signal_type.value}] {sig.observed_fact} "
                f"(date: {date_str}, source: {sig.source})"
            )

    # Pain hypotheses
    if pain_hypotheses:
        context_parts.append("\n## Pain Hypotheses")
        for ph in pain_hypotheses:
            facts_str = "; ".join(f.statement for f in ph.supporting_facts)
            context_parts.append(
                f"- {ph.pain_type.value} (score: {ph.score}, confidence: {ph.confidence_score}): "
                f"Facts: [{facts_str}] | Unknowns: {ph.unknowns}"
            )

    # Value propositions
    if value_props:
        context_parts.append("\n## Value Propositions")
        for vp in value_props:
            context_parts.append(
                f"- Problem: {vp.top_problem} | Capability: {vp.relevant_capability} | "
                f"Hook: {vp.one_line_hook} | Confidence: {vp.confidence_score}"
            )

    # Action recommendation
    if action_recommendation:
        context_parts.append("\n## Action Recommendation")
        context_parts.append(f"Action: {action_recommendation.action.value}")
        context_parts.append(f"Explanation: {action_recommendation.explanation}")
        if action_recommendation.best_first_contact:
            context_parts.append(
                f"Best First Contact: {action_recommendation.best_first_contact.name}"
            )

    user_prompt = (
        "\n".join(context_parts)
        + "\n\nSynthesize all the above into a concise seller brief. "
        "Return JSON with keys: account_snapshot, why_this_account, why_now, "
        "likely_pain_points, recommended_contacts, persona_angles, risks_and_unknowns."
    )

    try:
        raw = await call_claude(
            task="brief_generation",
            system=SYSTEM_BRIEF_BUILDER,
            user=user_prompt,
            workspace_id=workspace_id,
            model=settings.CLAUDE_MODEL,
        )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(
                "brief_builder.json_parse_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                raw=raw[:200],
            )
            data = {}

        # Collect sources from signals and enrichment
        sources_consulted: list[str] = []
        for sig in signals:
            if sig.source and sig.source not in sources_consulted:
                sources_consulted.append(sig.source)
        if enrichment:
            sources_consulted.append("enrichment_research")

        brief = SellerBrief(
            id=str(uuid4()),
            account_id=account.id,
            workspace_id=workspace_id,
            account_snapshot=data.get("account_snapshot", ""),
            why_this_account=data.get("why_this_account", ""),
            why_now=data.get("why_now", ""),
            likely_pain_points=pain_hypotheses,
            recommended_contacts=ranked_contacts[:3],
            persona_angles=value_props,
            risks_and_unknowns=data.get("risks_and_unknowns", []),
            recommended_action=action_recommendation or ActionRecommendation(
                action=ActionType.HUMAN_REVIEW_REQUIRED,
                explanation="No action recommendation available",
            ),
            signals_used=signals,
            sources_consulted=sources_consulted,
            scoring=account_score,
            generated_at=datetime.now(timezone.utc),
        )

        log.info("brief_builder.complete", thread_id=thread_id, workspace_id=workspace_id)
        return {"seller_brief": brief}

    except Exception as exc:
        log.error(
            "brief_builder.error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        return {"error": str(exc), "seller_brief": None}
