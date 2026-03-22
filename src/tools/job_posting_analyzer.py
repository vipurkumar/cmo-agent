"""JobPostingAnalyzerTool — detects hiring signals from job postings via n8n webhook."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class JobPostingError(Exception):
    """Raised on job posting analysis failures (including 429 and 401)."""


class JobPostingAnalyzerTool(BaseTool):
    """Detects hiring signals by searching and analyzing job postings for a company.

    Uses an n8n webhook to search job postings, then extracts hiring
    signals (growth indicators, tech stack shifts, new market expansion, etc.).

    Input: company name and optional domain.
    Output: dict with job postings and hiring signals.
    """

    RESOURCE_NAME = "web_scraper"

    def __init__(self, rate_limiter: RateLimiter) -> None:
        super().__init__(rate_limiter)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def run(
        self,
        company: str,
        workspace_id: str,
        plan: str,
        domain: str | None = None,
    ) -> dict[str, Any]:
        """Search for job postings and extract hiring signals.

        Parameters
        ----------
        company:
            The company name to search job postings for.
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace.
        domain:
            Optional company domain for more precise matching.

        Returns
        -------
        dict[str, Any]
            Dict with keys: ``company``, ``job_postings`` (list of
            ``{title, department, location, url}``), ``hiring_signals`` (list),
            ``total_openings``.
        """
        log.info(
            "job_posting_analyzer.start",
            company=company,
            workspace_id=workspace_id,
            domain=domain,
        )

        # 1. Rate limit check FIRST
        await self.rate_limiter.enforce(workspace_id, self.RESOURCE_NAME, plan)

        # 2. HTTP call with timeout
        payload: dict[str, Any] = {"company": company}
        if domain:
            payload["domain"] = domain

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.N8N_WEBHOOK_BASE_URL}/job-postings",
                headers={
                    "Content-Type": "application/json",
                    "X-Workspace-Id": workspace_id,
                },
                json=payload,
            )

        # 3. Specific error handling
        if resp.status_code == 429:
            raise JobPostingError(
                f"Rate limited by job postings endpoint for workspace {workspace_id}"
            )
        if resp.status_code == 401:
            raise JobPostingError("Invalid job postings endpoint credentials")
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        raw_postings: list[dict[str, Any]] = data.get("postings", data.get("jobs", []))

        # 4. Normalize job postings to standard shape
        job_postings = [
            {
                "title": posting.get("title", ""),
                "department": posting.get("department", posting.get("category", "")),
                "location": posting.get("location", ""),
                "url": posting.get("url", posting.get("link", "")),
            }
            for posting in raw_postings
        ]

        # 5. Extract hiring signals
        hiring_signals = _extract_hiring_signals(job_postings)

        result: dict[str, Any] = {
            "company": company,
            "job_postings": job_postings,
            "hiring_signals": hiring_signals,
            "total_openings": len(job_postings),
        }

        log.info(
            "job_posting_analyzer.complete",
            workspace_id=workspace_id,
            company=company,
            total_openings=result["total_openings"],
            signal_count=len(hiring_signals),
        )

        return result


# ---------------------------------------------------------------------------
# Private helpers for hiring signal extraction
# ---------------------------------------------------------------------------

_SIGNAL_RULES: dict[str, list[str]] = {
    "sales_expansion": [
        "account executive", "sales rep", "sdr", "bdr", "sales manager",
        "sales director", "head of sales", "vp sales",
    ],
    "engineering_growth": [
        "software engineer", "developer", "sre", "devops", "platform engineer",
        "engineering manager", "cto", "vp engineering",
    ],
    "marketing_investment": [
        "marketing manager", "demand gen", "content marketer", "growth marketer",
        "head of marketing", "vp marketing", "cmo",
    ],
    "international_expansion": [
        "emea", "apac", "latam", "europe", "asia", "international",
        "remote - global",
    ],
    "product_led_growth": [
        "product manager", "product designer", "ux researcher", "growth pm",
        "product-led",
    ],
    "data_and_analytics": [
        "data engineer", "data scientist", "analytics engineer", "bi analyst",
        "head of data",
    ],
    "revops_buildout": [
        "revenue operations", "revops", "sales operations", "salesops",
        "marketing operations", "deal desk",
    ],
    "finance_scaling": [
        "billing", "finance", "controller", "fp&a", "cfo", "accounting",
    ],
}


def _extract_hiring_signals(postings: list[dict[str, Any]]) -> list[str]:
    """Detect hiring signal categories from a list of job postings."""
    signals: list[str] = []
    all_titles = " ".join(p.get("title", "").lower() for p in postings)
    all_locations = " ".join(p.get("location", "").lower() for p in postings)
    combined = f"{all_titles} {all_locations}"

    for signal_name, keywords in _SIGNAL_RULES.items():
        if any(kw in combined for kw in keywords):
            signals.append(signal_name)

    # Volume-based signals
    if len(postings) >= 20:
        signals.append("high_volume_hiring")
    if len(postings) >= 50:
        signals.append("hypergrowth")

    return signals
