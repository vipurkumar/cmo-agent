"""ApolloSearchTool — searches Apollo API for contacts/companies matching ICP criteria."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class ApolloRateLimitError(Exception):
    """Raised when Apollo returns HTTP 429."""


class ApolloAuthError(Exception):
    """Raised when Apollo returns HTTP 401."""


class ApolloSearchTool(BaseTool):
    """Searches Apollo API for contacts/companies matching ICP criteria.

    Input: query string + filters dict.
    Output: list of matched contacts.
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
        query: str,
        workspace_id: str,
        plan: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search Apollo for contacts matching *query* and optional *filters*.

        Parameters
        ----------
        query:
            Free-text search string (e.g. company name, title keywords).
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace (``free``, ``pro``, ``enterprise``).
        filters:
            Optional dict of Apollo filter params (e.g. person_titles, industries).
        """
        log.info(
            "apollo_search.start",
            query=query,
            workspace_id=workspace_id,
        )

        # 1. Rate limit check FIRST
        await self.rate_limiter.enforce(workspace_id, "apollo", plan)

        # 2. Build request params
        params: dict[str, Any] = {"q": query}
        if filters:
            params.update(filters)

        # 3. HTTP call with timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.APOLLO_BASE_URL}/mixed_people/search",
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": settings.APOLLO_API_KEY,
                },
                json=params,
            )

        # 4. Specific error handling
        if resp.status_code == 429:
            raise ApolloRateLimitError(
                f"Rate limited by Apollo API for workspace {workspace_id}"
            )
        if resp.status_code == 401:
            raise ApolloAuthError("Invalid Apollo API credentials")
        resp.raise_for_status()

        data = resp.json()
        contacts: list[dict[str, Any]] = data.get("people", [])

        log.info(
            "apollo_search.complete",
            workspace_id=workspace_id,
            result_count=len(contacts),
        )

        return contacts
