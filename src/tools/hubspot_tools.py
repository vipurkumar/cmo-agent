"""HubSpotTool — CRUD operations on HubSpot CRM."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class HubSpotRateLimitError(Exception):
    """Raised when HubSpot returns HTTP 429."""


class HubSpotAuthError(Exception):
    """Raised when HubSpot returns HTTP 401."""


HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubSpotTool(BaseTool):
    """CRUD operations on HubSpot CRM.

    Supports creating/updating contacts, deals, and logging activities.
    Input varies by operation. Output: HubSpot record dict.
    """

    RESOURCE_NAME = "hubspot"

    def __init__(self, rate_limiter: RateLimiter) -> None:
        super().__init__(rate_limiter)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def run(
        self,
        operation: str,
        workspace_id: str,
        plan: str,
        object_type: str = "contacts",
        record_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a HubSpot CRM operation.

        Parameters
        ----------
        operation:
            One of ``"create"``, ``"update"``, ``"get"``, ``"log_activity"``.
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace.
        object_type:
            HubSpot object type: ``"contacts"``, ``"deals"``, ``"companies"``,
            ``"engagements"``.
        record_id:
            HubSpot record ID (required for ``update`` and ``get``).
        properties:
            Dict of properties to set (required for ``create`` and ``update``).

        Returns
        -------
        dict[str, Any]
            The HubSpot record as returned by the API.
        """
        log.info(
            "hubspot.start",
            operation=operation,
            object_type=object_type,
            record_id=record_id,
            workspace_id=workspace_id,
        )

        # 1. Rate limit check FIRST
        await self.rate_limiter.enforce(workspace_id, self.RESOURCE_NAME, plan)

        headers = {
            "Authorization": f"Bearer {settings.HUBSPOT_API_KEY}",
            "Content-Type": "application/json",
        }

        # 2. HTTP call with timeout — route by operation
        async with httpx.AsyncClient(timeout=10.0) as client:
            if operation == "create":
                resp = await client.post(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/{object_type}",
                    headers=headers,
                    json={"properties": properties or {}},
                )

            elif operation == "update":
                if not record_id:
                    raise ValueError("record_id is required for update operation")
                resp = await client.patch(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/{object_type}/{record_id}",
                    headers=headers,
                    json={"properties": properties or {}},
                )

            elif operation == "get":
                if not record_id:
                    raise ValueError("record_id is required for get operation")
                resp = await client.get(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/{object_type}/{record_id}",
                    headers=headers,
                )

            elif operation == "log_activity":
                resp = await client.post(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/engagements",
                    headers=headers,
                    json={"properties": properties or {}},
                )

            else:
                raise ValueError(f"Unknown HubSpot operation: {operation}")

        # 3. Specific error handling
        if resp.status_code == 429:
            raise HubSpotRateLimitError(
                f"Rate limited by HubSpot API for workspace {workspace_id}"
            )
        if resp.status_code == 401:
            raise HubSpotAuthError("Invalid HubSpot API credentials")
        resp.raise_for_status()

        record: dict[str, Any] = resp.json()

        log.info(
            "hubspot.complete",
            operation=operation,
            object_type=object_type,
            workspace_id=workspace_id,
        )

        return record
