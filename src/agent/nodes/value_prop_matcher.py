"""value_prop_matcher node — maps pain hypotheses to product value propositions.

Uses campaign_memory.search_similar() for pgvector semantic search, then
calls call_claude() with SYSTEM_VALUE_PROP_MATCHER to generate
persona-specific value propositions.
"""

from __future__ import annotations

import json

from src.agent.state import (
    Evidence,
    EvidenceType,
    QualificationState,
    ValuePropRecommendation,
)
from src.config import settings
from src.db.campaign_memory import search_similar
from src.llm.budget import call_claude
from src.llm.embeddings import embed_text
from src.llm.prompts import SYSTEM_VALUE_PROP_MATCHER
from src.logger import log

# Module-level DB session factory — injected at startup
_session_factory = None


def init_session_factory(session_factory) -> None:
    """Inject the async session factory (called once at app startup)."""
    global _session_factory
    _session_factory = session_factory


async def value_prop_matcher(state: QualificationState) -> dict:
    """Match pain hypotheses to product value propositions."""
    thread_id = state["thread_id"]
    account = state.get("current_account")
    if account is None:
        return {"error": "No current_account set"}

    workspace_id = account.workspace_id
    log.info("value_prop_matcher.start", thread_id=thread_id, workspace_id=workspace_id)

    pain_hypotheses = state.get("pain_hypotheses", [])
    ranked_contacts = state.get("ranked_contacts", [])
    kb_case_studies = state.get("kb_case_studies", [])
    kb_battlecards = state.get("kb_battlecards", [])
    kb_messaging = state.get("kb_messaging", [])

    # Semantic search for relevant case studies via pgvector
    similar_content: list[str] = []
    if _session_factory is not None and pain_hypotheses:
        try:
            pain_summary = " ".join(
                f"{ph.pain_type.value}: {'; '.join(ph.inferences[:2])}"
                for ph in pain_hypotheses[:3]
            )
            # Embed the pain summary for semantic search
            query_vector = await embed_text(pain_summary, input_type="query")
            campaign = state.get("campaign")
            campaign_id = campaign.id if campaign else "default"

            async with _session_factory() as session:
                memories = await search_similar(
                    session=session,
                    workspace_id=workspace_id,
                    campaign_id=campaign_id,
                    query_vector=query_vector,
                    top_k=5,
                )
                similar_content = [m.content for m in memories]
        except Exception as exc:
            log.warning(
                "value_prop_matcher.vector_search_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                error=str(exc),
            )

    # Build user prompt with all context
    context_parts = [
        "## Account",
        f"Name: {account.company_name}",
        f"Domain: {account.domain or 'N/A'}",
        f"Industry: {account.industry or 'N/A'}",
    ]

    # Pain hypotheses
    context_parts.append("\n## Pain Hypotheses")
    for ph in pain_hypotheses:
        facts_str = "; ".join(f.statement for f in ph.supporting_facts)
        context_parts.append(
            f"- {ph.pain_type.value} (score: {ph.score}, confidence: {ph.confidence_score}): "
            f"Facts: [{facts_str}] | Inferences: {ph.inferences}"
        )

    # Contacts
    context_parts.append("\n## Target Contacts")
    for rc in ranked_contacts[:5]:
        context_parts.append(
            f"- {rc.name} | {rc.title} | Role: {rc.likely_role.value} | "
            f"Relevance: {rc.relevance_score} | ID: {rc.contact_id}"
        )

    # Knowledge base context
    context_parts.append("\n## Knowledge Base — Case Studies")
    for cs in kb_case_studies:
        context_parts.append(f"- {cs}")
    for sc in similar_content:
        context_parts.append(f"- [vector match] {sc}")

    context_parts.append("\n## Knowledge Base — Battlecards")
    for bc in kb_battlecards:
        context_parts.append(f"- {bc}")

    context_parts.append("\n## Knowledge Base — Messaging")
    for msg in kb_messaging:
        context_parts.append(f"- {msg}")

    user_prompt = (
        "\n".join(context_parts)
        + "\n\nGenerate persona-specific value propositions. "
        "Return a JSON array of value proposition recommendation objects."
    )

    try:
        raw = await call_claude(
            task="value_prop_matching",
            system=SYSTEM_VALUE_PROP_MATCHER,
            user=user_prompt,
            workspace_id=workspace_id,
            model=settings.CLAUDE_MODEL,
        )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(
                "value_prop_matcher.json_parse_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                raw=raw[:200],
            )
            data = []

        # Normalize: accept both top-level array and wrapped object
        if isinstance(data, dict):
            data = data.get("recommendations", data.get("value_props", []))

        value_props: list[ValuePropRecommendation] = []
        for item in data:
            try:
                proof_point = None
                pp_data = item.get("proof_point")
                if pp_data and isinstance(pp_data, dict):
                    proof_point = Evidence(
                        statement=pp_data.get("statement", ""),
                        evidence_type=EvidenceType(pp_data.get("evidence_type", "fact")),
                        source=pp_data.get("source", "knowledge_base"),
                    )

                value_props.append(
                    ValuePropRecommendation(
                        contact_id=item.get("contact_id"),
                        top_problem=item.get("top_problem", ""),
                        relevant_capability=item.get("relevant_capability", ""),
                        expected_business_outcome=item.get("expected_business_outcome", ""),
                        one_line_hook=item.get("one_line_hook", ""),
                        short_value_prop=item.get("short_value_prop", ""),
                        likely_objection=item.get("likely_objection", ""),
                        suggested_response=item.get("suggested_response", ""),
                        proof_point=proof_point,
                        confidence_score=float(item.get("confidence_score", 0.0)),
                    )
                )
            except (KeyError, ValueError) as exc:
                log.warning(
                    "value_prop_matcher.item_parse_error",
                    thread_id=thread_id,
                    workspace_id=workspace_id,
                    error=str(exc),
                )
                continue

        log.info(
            "value_prop_matcher.complete",
            thread_id=thread_id,
            workspace_id=workspace_id,
            value_prop_count=len(value_props),
        )
        return {"value_props": value_props}

    except Exception as exc:
        log.error(
            "value_prop_matcher.error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        return {"error": str(exc), "value_props": []}
