"""personaliser node — generates a personalized email from enrichment data.

Uses ClaudeWriterTool to produce a PersonalizedEmail for the current
account/contact at the current sequence stage.
"""

from __future__ import annotations

from src.agent.state import OutboundState, PersonalizedEmail
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.claude_writer import ClaudeWriterTool

# Module-level tool — RateLimiter injected at startup
_rate_limiter: RateLimiter | None = None


def init_tools(rate_limiter: RateLimiter) -> None:
    """Inject the shared RateLimiter (called once at app startup)."""
    global _rate_limiter
    _rate_limiter = rate_limiter


def _get_tool() -> ClaudeWriterTool:
    if _rate_limiter is None:
        raise RuntimeError("personaliser tools not initialised — call init_tools() first")
    return ClaudeWriterTool(_rate_limiter)


async def personaliser(state: OutboundState) -> dict:
    """Generate a personalised email for the current account and stage."""
    thread_id = state["thread_id"]
    account = state["current_account"]
    if account is None:
        return {"error": "No current_account set"}

    workspace_id = account.workspace_id
    log.info("personaliser.start", thread_id=thread_id, workspace_id=workspace_id)

    enrichment = state.get("enrichment")
    contact = state.get("current_contact")
    current_stage = state.get("current_stage", 1)
    campaign = state.get("campaign")

    writer_tool = _get_tool()

    # Build research data dict for the writer
    research_data = {
        "company_name": account.company_name,
        "domain": account.domain,
        "industry": account.industry,
        "contact_name": (
            f"{contact.first_name or ''} {contact.last_name or ''}".strip()
            if contact else ""
        ),
        "contact_role": contact.role if contact else "",
        "stage": current_stage,
    }

    if enrichment:
        research_data.update({
            "company_summary": enrichment.company_summary,
            "recent_news": enrichment.recent_news,
            "pain_points": enrichment.pain_points,
            "technologies": enrichment.technologies,
        })

    # Determine template based on stage
    sequence_config = campaign.sequence_config if campaign else {}
    stages = sequence_config.get("stages", [])
    template = ""
    if stages and current_stage <= len(stages):
        template = stages[current_stage - 1].get("template", "")
    if not template:
        template = (
            f"Stage {current_stage} outbound email to {{contact_name}} at "
            f"{{company_name}}. Keep it concise and personalized."
        )

    hooks = enrichment.personalization_hooks if enrichment else []

    plan_name = "pro"  # default plan

    result = await writer_tool.run(
        research_data=research_data,
        template=template,
        personalization_hooks=hooks,
        workspace_id=workspace_id,
        plan=plan_name,
    )

    email = PersonalizedEmail(
        subject_line=result.get("subject", ""),
        body=result.get("body", ""),
        personalization_score=float(result.get("personalization_score", 0.0)),
    )

    log.info(
        "personaliser.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        subject_length=len(email.subject_line),
    )

    return {"draft_email": email}
