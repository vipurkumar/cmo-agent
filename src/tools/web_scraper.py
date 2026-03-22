"""WebScraperTool — scrapes a webpage for content."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class WebScraperRateLimitError(Exception):
    """Raised when the scraping endpoint returns HTTP 429."""


class WebScraperAuthError(Exception):
    """Raised when the scraping endpoint returns HTTP 401."""


class WebScraperTool(BaseTool):
    """Scrapes a webpage for content.

    Input: url.
    Output: extracted text content.
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
        url: str,
        workspace_id: str,
        plan: str,
    ) -> dict[str, Any]:
        """Scrape the webpage at *url* and return extracted text.

        Parameters
        ----------
        url:
            The URL of the page to scrape.
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace.

        Returns
        -------
        dict[str, Any]
            Dict with ``url``, ``title``, and ``content`` keys.
        """
        log.info(
            "web_scraper.start",
            url=url,
            workspace_id=workspace_id,
        )

        # 1. Rate limit check FIRST
        await self.rate_limiter.enforce(workspace_id, self.RESOURCE_NAME, plan)

        # 2. HTTP call with timeout (longer timeout for scraping)
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.N8N_WEBHOOK_BASE_URL}/web-scrape",
                headers={
                    "Content-Type": "application/json",
                    "X-Workspace-Id": workspace_id,
                },
                json={"url": url},
            )

        # 3. Specific error handling
        if resp.status_code == 429:
            raise WebScraperRateLimitError(
                f"Rate limited by web scraper for workspace {workspace_id}"
            )
        if resp.status_code == 401:
            raise WebScraperAuthError("Invalid web scraper credentials")
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()

        result = {
            "url": url,
            "title": data.get("title", ""),
            "content": data.get("content", data.get("text", "")),
        }

        log.info(
            "web_scraper.complete",
            workspace_id=workspace_id,
            url=url,
            content_length=len(result["content"]),
        )

        return result
