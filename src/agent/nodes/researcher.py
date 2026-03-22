"""researcher node — enriches the current account with company intel and news.

Uses ApolloSearchTool and NewsSearchTool for data gathering, then calls
call_claude() with SYSTEM_RESEARCHER to synthesize into an EnrichmentResult.
"""

from __future__ import annotations

import json

from src.agent.state import EnrichmentResult, OutboundState
from src.config import settings
from src.llm.budget import call_claude
from src.llm.prompts import SYSTEM_RESEARCHER
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.apollo_search import ApolloSearchTool
from src.tools.news_search import NewsSearchTool

# Module-level tool instances — RateLimiter is injected at startup
_rate_limiter: RateLimiter | None = None


def init_tools(rate_limiter: RateLimiter) -> None:
    """Inject the shared RateLimiter (called once at app startup)."""
    global _rate_limiter
    _rate_limiter = rate_limiter


def _get_tools() -> tuple[ApolloSearchTool, NewsSearchTool]:
    if _rate_limiter is None:
        raise RuntimeError("researcher tools not initialised — call init_tools() first")
    return ApolloSearchTool(_rate_limiter), NewsSearchTool(_rate_limiter)


async def researcher(state: OutboundState) -> dict:
    """Research the current account and produce an EnrichmentResult."""
    thread_id = state["thread_id"]
    account = state["current_account"]
    if account is None:
        return {"error": "No current_account set"}

    workspace_id = account.workspace_id
    log.info("researcher.start", thread_id=thread_id, workspace_id=workspace_id)

    apollo_tool, news_tool = _get_tools()
    plan = state.get("campaign")
    plan_name = (
        plan.metadata.get("plan", "pro")
        if plan and hasattr(plan, "metadata")
        else "pro"
    ) if plan else "pro"

    try:
        # Gather data in parallel-safe fashion
        apollo_results = await apollo_tool.run(
            query=account.company_name,
            workspace_id=workspace_id,
            plan=plan_name,
            filters={"domain": account.domain} if account.domain else None,
        )

        news_results = await news_tool.run(
            company=account.company_name,
            workspace_id=workspace_id,
            plan=plan_name,
        )

        # Synthesize findings via Claude
        user_prompt = (
            f"## Company\n"
            f"Name: {account.company_name}\n"
            f"Domain: {account.domain or 'N/A'}\n"
            f"Industry: {account.industry or 'N/A'}\n\n"
            f"## Apollo Data\n{json.dumps(apollo_results[:10], indent=2)}\n\n"
            f"## Recent News\n{json.dumps(news_results[:10], indent=2)}\n\n"
            "Synthesize the above into a research brief. "
            "Return JSON with keys: company_summary, recent_news, pain_points, "
            "personalization_hooks, technologies."
        )

        raw = await call_claude(
            task="research",
            system=SYSTEM_RESEARCHER,
            user=user_prompt,
            workspace_id=workspace_id,
            model=settings.CLAUDE_MODEL,
        )

        # Parse response
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(
                "researcher.json_parse_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                raw=raw[:200],
            )
            data = {
                "company_summary": raw,
                "recent_news": [],
                "pain_points": [],
                "personalization_hooks": [],
                "technologies": [],
            }

        enrichment = EnrichmentResult(
            company_summary=data.get("company_summary", ""),
            recent_news=data.get("recent_news", data.get("recent_signals", [])),
            pain_points=data.get("pain_points", []),
            personalization_hooks=data.get(
                "personalization_hooks",
                data.get("personalisation_hooks", []),
            ),
            technologies=data.get("technologies", []),
        )

        log.info("researcher.complete", thread_id=thread_id, workspace_id=workspace_id)
        return {"enrichment": enrichment}

    except Exception as exc:
        log.error(
            "researcher.error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        return {"error": str(exc), "enrichment": None}
