"""pain_inferrer node — generates ranked pain hypotheses from account evidence.

Uses call_claude() with SYSTEM_PAIN_INFERRER to infer pain points from
account data, signals, and enrichment results.
"""

from __future__ import annotations

import json

from src.agent.state import (
    Evidence,
    EvidenceType,
    PainHypothesis,
    PainType,
    QualificationState,
)
from src.config import settings
from src.llm.budget import call_claude
from src.llm.prompts import SYSTEM_PAIN_INFERRER
from src.logger import log


async def pain_inferrer(state: QualificationState) -> dict:
    """Infer pain hypotheses from account signals and enrichment data."""
    thread_id = state["thread_id"]
    account = state.get("current_account")
    if account is None:
        return {"error": "No current_account set"}

    workspace_id = account.workspace_id
    log.info("pain_inferrer.start", thread_id=thread_id, workspace_id=workspace_id)

    signals = state.get("signals", [])
    enrichment = state.get("enrichment")

    # Build context string with account info
    context_parts = [
        "## Account",
        f"Name: {account.company_name}",
        f"Domain: {account.domain or 'N/A'}",
        f"Industry: {account.industry or 'N/A'}",
        f"Employee Count: {account.employee_count or 'N/A'}",
        f"Revenue: {account.revenue or 'N/A'}",
    ]

    # Add signals
    if signals:
        context_parts.append("\n## Signals")
        for sig in signals:
            context_parts.append(
                f"- [{sig.signal_type.value}] Observed: {sig.observed_fact} | "
                f"Implication: {sig.possible_implication} "
                f"(confidence: {sig.confidence}, source: {sig.source})"
            )

    # Add enrichment data
    if enrichment:
        context_parts.append("\n## Enrichment Data")
        context_parts.append(f"Summary: {enrichment.company_summary}")
        if enrichment.pain_points:
            context_parts.append(f"Known Pain Points: {json.dumps(enrichment.pain_points)}")
        if enrichment.technologies:
            context_parts.append(f"Technologies: {json.dumps(enrichment.technologies)}")
        if enrichment.recent_news:
            context_parts.append(f"Recent News: {json.dumps(enrichment.recent_news)}")

    user_prompt = (
        "\n".join(context_parts)
        + "\n\nAnalyze the above and generate ranked pain hypotheses. "
        "Return a JSON array of pain hypothesis objects."
    )

    try:
        raw = await call_claude(
            task="pain_inference",
            system=SYSTEM_PAIN_INFERRER,
            user=user_prompt,
            workspace_id=workspace_id,
            model=settings.CLAUDE_MODEL,
        )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(
                "pain_inferrer.json_parse_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                raw=raw[:200],
            )
            data = []

        # Normalize: accept both top-level array and {"hypotheses": [...]}
        if isinstance(data, dict):
            data = data.get("hypotheses", data.get("pain_hypotheses", []))

        hypotheses: list[PainHypothesis] = []
        for item in data:
            try:
                supporting_facts = [
                    Evidence(
                        statement=e.get("statement", ""),
                        evidence_type=EvidenceType(e.get("evidence_type", "unknown")),
                        source=e.get("source", "llm_inference"),
                    )
                    for e in item.get("supporting_facts", [])
                ]
                hypotheses.append(
                    PainHypothesis(
                        pain_type=PainType(item["pain_type"]),
                        score=int(item.get("score", 0)),
                        supporting_facts=supporting_facts,
                        inferences=item.get("inferences", []),
                        unknowns=item.get("unknowns", []),
                        confidence_score=float(item.get("confidence_score", 0.0)),
                    )
                )
            except (KeyError, ValueError) as exc:
                log.warning(
                    "pain_inferrer.item_parse_error",
                    thread_id=thread_id,
                    workspace_id=workspace_id,
                    error=str(exc),
                )
                continue

        # Sort by score descending
        hypotheses.sort(key=lambda h: h.score, reverse=True)

        log.info(
            "pain_inferrer.complete",
            thread_id=thread_id,
            workspace_id=workspace_id,
            hypothesis_count=len(hypotheses),
        )
        return {"pain_hypotheses": hypotheses}

    except Exception as exc:
        log.error(
            "pain_inferrer.error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        return {"error": str(exc), "pain_hypotheses": []}
