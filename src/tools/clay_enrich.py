"""ClayEnrichTool — enriches contact/company data via Clay API."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class ClayRateLimitError(Exception):
    """Raised when Clay returns HTTP 429."""


class ClayAuthError(Exception):
    """Raised when Clay returns HTTP 401."""


class ClayEnrichTool(BaseTool):
    """Enriches contact/company data via the Clay API.

    Input: contact email or company domain.
    Output: enriched data dict.
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
        identifier: str,
        workspace_id: str,
        plan: str,
        identifier_type: str = "email",
    ) -> dict[str, Any]:
        """Enrich a contact or company via Clay.

        Parameters
        ----------
        identifier:
            Contact email address or company domain to enrich.
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace.
        identifier_type:
            Either ``"email"`` (default) or ``"domain"``.
        """
        log.info(
            "clay_enrich.start",
            identifier=identifier,
            identifier_type=identifier_type,
            workspace_id=workspace_id,
        )

        # 1. Rate limit check FIRST
        await self.rate_limiter.enforce(workspace_id, "clay", plan)

        # 2. Build request payload
        payload: dict[str, Any] = {identifier_type: identifier}

        # 3. HTTP call with timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.CLAY_BASE_URL}/enrich",
                headers={
                    "Authorization": f"Bearer {settings.CLAY_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        # 4. Specific error handling
        if resp.status_code == 429:
            raise ClayRateLimitError(
                f"Rate limited by Clay API for workspace {workspace_id}"
            )
        if resp.status_code == 401:
            raise ClayAuthError("Invalid Clay API credentials")
        resp.raise_for_status()

        enriched_data: dict[str, Any] = resp.json()

        log.info(
            "clay_enrich.complete",
            workspace_id=workspace_id,
            identifier=identifier,
        )

        return enriched_data
