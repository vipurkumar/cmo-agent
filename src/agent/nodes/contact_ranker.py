"""contact_ranker node — ranks contacts and assembles buying committee.

Calls call_claude() with SYSTEM_CONTACT_RANKER (Sonnet) to rank contacts
by relevance and map them to buying committee roles.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from src.agent.state import (
    BuyingCommittee,
    BuyingRole,
    Contact,
    Evidence,
    EvidenceType,
    PainHypothesis,
    QualificationState,
    RankedContact,
)
from src.config import settings
from src.llm.budget import call_claude
from src.llm.prompts import SYSTEM_CONTACT_RANKER
from src.logger import log

# Valid buying roles for safe parsing
_VALID_ROLES = {r.value for r in BuyingRole}


async def contact_ranker(state: QualificationState) -> dict:
    """Rank contacts and assemble the buying committee."""
    thread_id = state["thread_id"]
    workspace_id = state["workspace_id"]
    account = state.get("current_account")
    contacts: list[Contact] = state.get("contacts") or []
    pain_hypotheses: list[PainHypothesis] = state.get("pain_hypotheses") or []

    if account is None:
        return {"error": "No current_account set"}

    if not contacts:
        log.warning(
            "contact_ranker.no_contacts",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        return {"ranked_contacts": [], "buying_committee": None}

    log.info(
        "contact_ranker.start",
        thread_id=thread_id,
        workspace_id=workspace_id,
        account_id=account.id,
        contact_count=len(contacts),
    )

    # --- Build context for LLM ---
    contacts_data = []
    for c in contacts:
        contacts_data.append({
            "contact_id": c.id,
            "name": f"{c.first_name or ''} {c.last_name or ''}".strip() or "Unknown",
            "title": c.role or "Unknown",
            "email": c.email,
        })

    pain_context = []
    for ph in pain_hypotheses:
        pain_context.append({
            "pain_type": ph.pain_type.value,
            "score": ph.score,
            "inferences": ph.inferences[:3],  # limit for token efficiency
        })

    user_prompt = (
        f"## Account\n"
        f"Name: {account.company_name}\n"
        f"Domain: {account.domain or 'N/A'}\n"
        f"Industry: {account.industry or 'N/A'}\n"
        f"Employee Count: {account.employee_count or 'N/A'}\n\n"
        f"## Pain Hypotheses\n{json.dumps(pain_context, indent=2)}\n\n"
        f"## Contacts\n{json.dumps(contacts_data, indent=2)}\n\n"
        "Rank these contacts by relevance to the account's pain points. "
        "Map each to a buying committee role. "
        "Return a JSON array of ranked contact objects."
    )

    try:
        raw = await call_claude(
            task="contact_ranking",
            system=SYSTEM_CONTACT_RANKER,
            user=user_prompt,
            workspace_id=workspace_id,
            model=settings.CLAUDE_MODEL,
        )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(
                "contact_ranker.json_parse_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                raw=raw[:200],
            )
            return {"ranked_contacts": [], "buying_committee": None}

        if not isinstance(parsed, list):
            parsed = [parsed] if isinstance(parsed, dict) else []

        # Build typed RankedContact objects
        ranked_contacts: list[RankedContact] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue

            # Validate buying role
            role_str = item.get("likely_role", "unknown")
            if role_str not in _VALID_ROLES:
                role_str = "unknown"

            # Parse evidence if provided
            evidence: list[Evidence] = []
            for ev_data in item.get("evidence", []):
                if isinstance(ev_data, dict):
                    evidence.append(Evidence(
                        statement=ev_data.get("statement", ""),
                        evidence_type=EvidenceType.INFERENCE,
                        source="contact_ranker_llm",
                        confidence=float(ev_data.get("confidence", 0.5)),
                    ))

            ranked = RankedContact(
                contact_id=item.get("contact_id", ""),
                name=item.get("name", "Unknown"),
                title=item.get("title", "Unknown"),
                normalized_function=item.get("normalized_function", "Other"),
                normalized_seniority=item.get("normalized_seniority", "Unknown"),
                relevance_score=max(0, min(100, int(item.get("relevance_score", 0)))),
                likely_role=BuyingRole(role_str),
                reason_for_relevance=item.get("reason_for_relevance", ""),
                confidence_score=float(item.get("confidence_score", 0.5)),
                evidence=evidence,
            )
            ranked_contacts.append(ranked)

        # Sort by relevance score descending
        ranked_contacts.sort(key=lambda r: r.relevance_score, reverse=True)

        # Assemble buying committee
        buying_committee = BuyingCommittee(
            account_id=account.id,
            workspace_id=workspace_id,
            ranked_contacts=ranked_contacts,
            committee_confidence=_compute_committee_confidence(ranked_contacts),
            mapped_at=datetime.now(tz=timezone.utc),
        )

        log.info(
            "contact_ranker.complete",
            thread_id=thread_id,
            workspace_id=workspace_id,
            account_id=account.id,
            ranked_count=len(ranked_contacts),
            committee_confidence=buying_committee.committee_confidence,
        )
        return {
            "ranked_contacts": ranked_contacts,
            "buying_committee": buying_committee,
        }

    except Exception as exc:
        log.error(
            "contact_ranker.error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        return {
            "ranked_contacts": [],
            "buying_committee": None,
            "error": str(exc),
        }


def _compute_committee_confidence(ranked_contacts: list[RankedContact]) -> float:
    """Compute overall confidence in the buying committee mapping.

    Higher confidence when:
    - Multiple roles are filled (not all 'unknown')
    - Individual contact confidences are high
    - At least one economic_buyer or pain_owner is identified
    """
    if not ranked_contacts:
        return 0.0

    # Average individual confidence
    avg_confidence = sum(r.confidence_score for r in ranked_contacts) / len(ranked_contacts)

    # Role coverage bonus
    filled_roles = {r.likely_role for r in ranked_contacts if r.likely_role != BuyingRole.UNKNOWN}
    coverage_bonus = min(0.3, len(filled_roles) * 0.06)

    # Key role bonus
    key_roles = {BuyingRole.ECONOMIC_BUYER, BuyingRole.PAIN_OWNER}
    has_key_role = bool(filled_roles & key_roles)
    key_bonus = 0.15 if has_key_role else 0.0

    return min(1.0, round(avg_confidence + coverage_bonus + key_bonus, 3))
