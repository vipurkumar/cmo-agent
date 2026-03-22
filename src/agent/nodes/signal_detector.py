"""signal_detector node — gathers raw text and classifies GTM signals.

Uses news_search and web_scraper tools for data gathering, then calls
call_claude() with SYSTEM_SIGNAL_CLASSIFIER (Haiku) to extract signals.

Also pulls Apollo job postings (via ApolloMCPAdapter) to provide real
hiring signals (pricing hires, RevOps hires, etc.).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from src.agent.state import QualificationState, Signal, SignalType
from src.config import settings
from src.llm.budget import call_claude
from src.llm.prompts import SYSTEM_SIGNAL_CLASSIFIER
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.scoring.timing_rules import _recency_score
from src.tools.news_search import NewsSearchTool
from src.tools.web_scraper import WebScraperTool

# Module-level tool instances — RateLimiter is injected at startup
_rate_limiter: RateLimiter | None = None


def init_tools(rate_limiter: RateLimiter) -> None:
    """Inject the shared RateLimiter (called once at app startup)."""
    global _rate_limiter
    _rate_limiter = rate_limiter


def _get_tools() -> tuple[NewsSearchTool, WebScraperTool]:
    if _rate_limiter is None:
        raise RuntimeError(
            "signal_detector tools not initialised — call init_tools() first"
        )
    return NewsSearchTool(_rate_limiter), WebScraperTool(_rate_limiter)


def _get_apollo_adapter():
    """Lazy-import ApolloMCPAdapter to avoid circular imports."""
    if _rate_limiter is None:
        return None
    try:
        from src.tools.apollo_mcp import ApolloMCPAdapter

        return ApolloMCPAdapter(_rate_limiter)
    except Exception:
        return None


# Valid signal types for safe parsing
_VALID_SIGNAL_TYPES = {t.value for t in SignalType}


async def signal_detector(state: QualificationState) -> dict:
    """Detect GTM signals for the current account."""
    thread_id = state["thread_id"]
    workspace_id = state["workspace_id"]
    account = state.get("current_account")

    if account is None:
        return {"error": "No current_account set"}

    log.info(
        "signal_detector.start",
        thread_id=thread_id,
        workspace_id=workspace_id,
        account_id=account.id,
    )

    news_tool, web_tool = _get_tools()
    plan = state.get("campaign")
    plan_name = (
        plan.icp_criteria.get("plan", "pro") if plan else "pro"
    )

    # --- Gather raw text from news and web ---
    raw_texts: list[str] = []

    # News search
    try:
        news_results = await news_tool.run(
            company=account.company_name,
            workspace_id=workspace_id,
            plan=plan_name,
        )
        for article in news_results:
            text = f"[NEWS] {article.get('title', '')} — {article.get('summary', '')}"
            raw_texts.append(text)
    except Exception as exc:
        log.warning(
            "signal_detector.news_search_failed",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )

    # Web scrape the company domain (pricing page, careers, blog)
    if account.domain:
        for page_path in ["/pricing", "/careers", "/blog"]:
            try:
                url = f"https://{account.domain}{page_path}"
                result = await web_tool.run(
                    url=url,
                    workspace_id=workspace_id,
                    plan=plan_name,
                )
                content = result.get("content", "")
                if content:
                    # Truncate to avoid token overload
                    raw_texts.append(
                        f"[WEB:{page_path}] {content[:2000]}"
                    )
            except Exception as exc:
                log.warning(
                    "signal_detector.web_scrape_failed",
                    thread_id=thread_id,
                    workspace_id=workspace_id,
                    url=f"https://{account.domain}{page_path}",
                    error=str(exc),
                )

    # --- Apollo job postings for hiring signal detection ---
    if account.domain and settings.USE_APOLLO_ENRICHMENT:
        apollo_adapter = _get_apollo_adapter()
        if apollo_adapter:
            try:
                job_postings = await apollo_adapter.get_job_postings(
                    domain=account.domain,
                    workspace_id=workspace_id,
                )
                if job_postings:
                    posting_lines: list[str] = []
                    for jp in job_postings:
                        title = jp.get("title", "")
                        dept = jp.get("department", "")
                        loc = jp.get("location", "")
                        line = f"  - {title}"
                        if dept:
                            line += f" ({dept})"
                        if loc:
                            line += f" [{loc}]"
                        posting_lines.append(line)

                    raw_texts.append(
                        f"[HIRING] {len(job_postings)} open positions at "
                        f"{account.company_name}:\n"
                        + "\n".join(posting_lines[:50])  # Cap at 50 postings
                    )
                    log.info(
                        "signal_detector.apollo_job_postings_loaded",
                        thread_id=thread_id,
                        workspace_id=workspace_id,
                        account_id=account.id,
                        posting_count=len(job_postings),
                    )
            except Exception as exc:
                log.warning(
                    "signal_detector.apollo_job_postings_failed",
                    thread_id=thread_id,
                    workspace_id=workspace_id,
                    account_id=account.id,
                    error=str(exc),
                )

    if not raw_texts:
        log.info(
            "signal_detector.no_raw_text",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        return {"signals": []}

    # --- Classify signals via Haiku ---
    combined_text = "\n\n".join(raw_texts)
    # Truncate combined text to fit within token budget
    if len(combined_text) > 15000:
        combined_text = combined_text[:15000]

    user_prompt = (
        f"## Company: {account.company_name}\n"
        f"Domain: {account.domain or 'N/A'}\n"
        f"Industry: {account.industry or 'N/A'}\n\n"
        f"## Raw Text\n{combined_text}\n\n"
        "Identify and classify GTM-relevant signals from the text above. "
        "Return a JSON array of signal objects."
    )

    try:
        raw = await call_claude(
            task="signal_classification",
            system=SYSTEM_SIGNAL_CLASSIFIER,
            user=user_prompt,
            workspace_id=workspace_id,
            model=settings.CLAUDE_HAIKU_MODEL,
        )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(
                "signal_detector.json_parse_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                raw=raw[:200],
            )
            return {"signals": []}

        if not isinstance(parsed, list):
            parsed = [parsed] if isinstance(parsed, dict) else []

        # Build typed Signal objects
        signals: list[Signal] = []
        now = datetime.now(tz=timezone.utc)

        for item in parsed:
            if not isinstance(item, dict):
                continue

            signal_type_str = item.get("signal_type", "")
            if signal_type_str not in _VALID_SIGNAL_TYPES:
                log.warning(
                    "signal_detector.unknown_signal_type",
                    thread_id=thread_id,
                    signal_type=signal_type_str,
                )
                continue

            # Parse event date if provided
            event_date: datetime | None = None
            raw_date = item.get("event_date")
            if raw_date:
                try:
                    event_date = datetime.fromisoformat(str(raw_date))
                    if event_date.tzinfo is None:
                        event_date = event_date.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    event_date = None

            # Compute recency score
            recency = _recency_score(event_date, now)

            signal = Signal(
                id=str(uuid.uuid4()),
                account_id=account.id,
                workspace_id=workspace_id,
                signal_type=SignalType(signal_type_str),
                source=item.get("source", "signal_detector"),
                observed_fact=item.get("observed_fact", ""),
                possible_implication=item.get("possible_implication", ""),
                event_date=event_date,
                recency_score=round(recency, 3),
                reliability_score=float(item.get("reliability_score", 0.5)),
                confidence=float(item.get("confidence", 0.5)),
                source_url=item.get("source_url"),
            )
            signals.append(signal)

        log.info(
            "signal_detector.complete",
            thread_id=thread_id,
            workspace_id=workspace_id,
            account_id=account.id,
            signal_count=len(signals),
        )
        return {"signals": signals}

    except Exception as exc:
        log.error(
            "signal_detector.error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            error=str(exc),
        )
        return {"signals": [], "error": str(exc)}
