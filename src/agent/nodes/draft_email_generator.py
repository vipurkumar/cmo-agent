"""draft_email_generator node — generates personalized draft emails without sending.

Runs after auto_outbound_gate when OUTBOUND_DRAFT_ONLY is True or when the
action is pursue_now. Uses ClaudeWriterTool to generate emails for the top
ranked contacts, storing results in state as DraftEmail objects.

No emails are sent — they're stored for customer review and manual action.
"""

from __future__ import annotations

import json

from src.agent.state import ActionType, DraftEmail, QualificationState
from src.config import settings
from src.llm.budget import call_claude
from src.logger import log
from src.ratelimit.bucket import RateLimiter

# Module-level tool — RateLimiter injected at startup
_rate_limiter: RateLimiter | None = None


def init_tools(rate_limiter: RateLimiter) -> None:
    """Inject the shared RateLimiter (called once at app startup)."""
    global _rate_limiter
    _rate_limiter = rate_limiter


async def draft_email_generator(state: QualificationState) -> dict:
    """Generate personalised draft emails for top contacts of the current account.

    Reads the seller brief, value props, and ranked contacts to produce
    targeted outreach emails. Returns ``draft_emails`` list in state.
    """
    thread_id = state.get("thread_id", "")
    account = state.get("current_account")
    if account is None:
        return {"draft_emails": []}

    workspace_id = account.workspace_id
    log.info("draft_email_generator.start", thread_id=thread_id, workspace_id=workspace_id)

    # Only generate drafts for pursue_now accounts
    recommendation = state.get("action_recommendation")
    if not recommendation or recommendation.action != ActionType.PURSUE_NOW:
        log.info(
            "draft_email_generator.skipped",
            thread_id=thread_id,
            workspace_id=workspace_id,
            reason=f"action={recommendation.action.value if recommendation else 'none'}",
        )
        return {"draft_emails": []}

    seller_brief = state.get("seller_brief")
    ranked_contacts = state.get("ranked_contacts", [])
    value_props = state.get("value_props", [])
    contacts = state.get("contacts", [])

    if not ranked_contacts:
        log.warning(
            "draft_email_generator.no_contacts",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        return {"draft_emails": []}

    # Build a contact email lookup
    contact_email_map: dict[str, str] = {}
    for c in contacts:
        contact_email_map[c.id] = c.email

    # Generate emails for top 3 contacts
    draft_emails: list[DraftEmail] = []
    top_contacts = ranked_contacts[:3]

    for rc in top_contacts:
        contact_email = contact_email_map.get(rc.contact_id, "")
        if not contact_email:
            continue

        # Find matching value prop for this contact
        matching_vp = None
        for vp in value_props:
            if vp.contact_id == rc.contact_id:
                matching_vp = vp
                break
        if not matching_vp and value_props:
            matching_vp = value_props[0]

        # Build context for email generation
        research_data = {
            "company_name": account.company_name,
            "domain": account.domain,
            "industry": account.industry,
            "contact_name": rc.name,
            "contact_title": rc.title,
            "contact_role": rc.likely_role.value,
            "why_this_account": seller_brief.why_this_account if seller_brief else "",
            "why_now": seller_brief.why_now if seller_brief else "",
        }

        if matching_vp:
            research_data.update({
                "top_problem": matching_vp.top_problem,
                "relevant_capability": matching_vp.relevant_capability,
                "one_line_hook": matching_vp.one_line_hook,
                "expected_outcome": matching_vp.expected_business_outcome,
                "likely_objection": matching_vp.likely_objection,
            })

        system_prompt = (
            "You are an expert B2B email copywriter. Write a concise, "
            "personalized cold outreach email that feels human and drives replies. "
            "The email should reference specific facts about the company and the "
            "contact's role. Keep it under 150 words. "
            "Output valid JSON with exactly two keys: \"subject\" and \"body\". "
            "No markdown, no extra keys."
        )

        user_prompt = (
            f"## Research Data\n{json.dumps(research_data, indent=2)}\n\n"
            "Generate a personalized outreach email for this contact. "
            "Reference their specific role and the company's situation. "
            "Return JSON: {\"subject\": \"...\", \"body\": \"...\"}"
        )

        try:
            raw = await call_claude(
                task="email_generation",
                system=system_prompt,
                user=user_prompt,
                workspace_id=workspace_id,
                model=settings.CLAUDE_MODEL,
            )

            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                result = {"subject": "Follow-up", "body": raw}

            draft = DraftEmail(
                account_id=account.id,
                contact_id=rc.contact_id,
                contact_name=rc.name,
                contact_email=contact_email,
                subject_line=result.get("subject", ""),
                body=result.get("body", ""),
                personalization_score=float(result.get("personalization_score", 0.0)),
                value_prop_used=matching_vp.one_line_hook if matching_vp else "",
                stage=1,
            )
            draft_emails.append(draft)

            log.info(
                "draft_email_generator.email_generated",
                thread_id=thread_id,
                workspace_id=workspace_id,
                contact_name=rc.name,
                subject_length=len(draft.subject_line),
            )

        except Exception as exc:
            log.warning(
                "draft_email_generator.generation_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                contact_name=rc.name,
                error=str(exc),
            )

    log.info(
        "draft_email_generator.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        drafts_generated=len(draft_emails),
    )
    return {"draft_emails": draft_emails}
