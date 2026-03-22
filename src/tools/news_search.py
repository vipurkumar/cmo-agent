"""NewsSearchTool — searches for recent news about a company."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class NewsSearchRateLimitError(Exception):
    """Raised when the news API returns HTTP 429."""


class NewsSearchAuthError(Exception):
    """Raised when the news API returns HTTP 401."""


class NewsSearchTool(BaseTool):
    """Searches for recent news about a company.

    Input: company name or domain.
    Output: list of news items with title, url, date, summary.
    """

    RESOURCE_NAME = "news"

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
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for recent news about *company*.

        Parameters
        ----------
        company:
            Company name or domain to search news for.
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace.
        max_results:
            Maximum number of news items to return (default 10).

        Returns
        -------
        list[dict[str, Any]]
            Each dict contains ``title``, ``url``, ``date``, and ``summary``.
        """
        log.info(
            "news_search.start",
            company=company,
            workspace_id=workspace_id,
        )

        # 1. Rate limit check FIRST
        await self.rate_limiter.enforce(workspace_id, self.RESOURCE_NAME, plan)

        # 2. HTTP call with timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.N8N_WEBHOOK_BASE_URL}/news-search",
                headers={"X-Workspace-Id": workspace_id},
                params={"company": company, "max_results": max_results},
            )

        # 3. Specific error handling
        if resp.status_code == 429:
            raise NewsSearchRateLimitError(
                f"Rate limited by news API for workspace {workspace_id}"
            )
        if resp.status_code == 401:
            raise NewsSearchAuthError("Invalid news API credentials")
        resp.raise_for_status()

        data = resp.json()
        articles: list[dict[str, Any]] = data.get("articles", [])

        # Normalize each article to the expected shape
        results = [
            {
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                "date": article.get("date", article.get("published_at", "")),
                "summary": article.get("summary", article.get("description", "")),
            }
            for article in articles[:max_results]
        ]

        log.info(
            "news_search.complete",
            workspace_id=workspace_id,
            result_count=len(results),
        )

        return results
