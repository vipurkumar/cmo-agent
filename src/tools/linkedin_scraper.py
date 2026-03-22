"""LinkedInScraperTool — fetches LinkedIn profile data."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class LinkedInRateLimitError(Exception):
    """Raised when the LinkedIn API returns HTTP 429."""


class LinkedInAuthError(Exception):
    """Raised when the LinkedIn API returns HTTP 401."""


class LinkedInScraperTool(BaseTool):
    """Fetches LinkedIn profile data.

    Input: linkedin_url or name+company.
    Output: profile data dict.
    """

    def __init__(self, rate_limiter: RateLimiter) -> None:
        super().__init__(rate_limiter)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def run(
        self,
        workspace_id: str,
        plan: str,
        linkedin_url: str | None = None,
        name: str | None = None,
        company: str | None = None,
    ) -> dict[str, Any]:
        """Fetch LinkedIn profile data.

        Provide either *linkedin_url* or both *name* and *company*.

        Parameters
        ----------
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace.
        linkedin_url:
            Direct LinkedIn profile URL.
        name:
            Person's full name (used with *company* for lookup).
        company:
            Company name (used with *name* for lookup).
        """
        if not linkedin_url and not (name and company):
            raise ValueError(
                "Provide either linkedin_url or both name and company"
            )

        log.info(
            "linkedin_scraper.start",
            linkedin_url=linkedin_url,
            name=name,
            company=company,
            workspace_id=workspace_id,
        )

        # 1. Rate limit check FIRST
        await self.rate_limiter.enforce(workspace_id, "linkedin", plan)

        # 2. Build request params
        params: dict[str, Any] = {}
        if linkedin_url:
            params["linkedin_url"] = linkedin_url
        else:
            params["name"] = name
            params["company"] = company

        # 3. HTTP call with timeout
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{settings.N8N_WEBHOOK_BASE_URL}/linkedin-profile",
                headers={
                    "Authorization": f"Bearer {settings.LINKEDIN_API_KEY}",
                    "X-Workspace-Id": workspace_id,
                },
                params=params,
            )

        # 4. Specific error handling
        if resp.status_code == 429:
            raise LinkedInRateLimitError(
                f"Rate limited by LinkedIn API for workspace {workspace_id}"
            )
        if resp.status_code == 401:
            raise LinkedInAuthError("Invalid LinkedIn API credentials")
        resp.raise_for_status()

        profile_data: dict[str, Any] = resp.json()

        log.info(
            "linkedin_scraper.complete",
            workspace_id=workspace_id,
        )

        return profile_data
