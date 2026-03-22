"""CRMReaderTool — reads account, contact, and deal data from HubSpot CRM."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class CRMReaderError(Exception):
    """Raised on general CRM reader failures."""


class CRMAuthError(Exception):
    """Raised when HubSpot returns HTTP 401."""


HUBSPOT_API_BASE = "https://api.hubapi.com"


class CRMReaderTool(BaseTool):
    """Reads account, contact, and deal data from HubSpot CRM.

    Supported operations: list_accounts, get_account, list_contacts,
    get_deals, get_deal_history.
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
        record_id: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Execute a HubSpot CRM read operation.

        Parameters
        ----------
        operation:
            One of ``"list_accounts"``, ``"get_account"``, ``"list_contacts"``,
            ``"get_deals"``, ``"get_deal_history"``.
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace.
        record_id:
            HubSpot record ID (required for ``get_account``, ``get_deal_history``).
        filters:
            Optional dict of filter params for list operations.
        limit:
            Maximum number of records to return for list operations.

        Returns
        -------
        dict[str, Any]
            Dict with operation-specific results.
        """
        log.info(
            "crm_reader.start",
            operation=operation,
            workspace_id=workspace_id,
            record_id=record_id,
        )

        # 1. Rate limit check FIRST
        await self.rate_limiter.enforce(workspace_id, self.RESOURCE_NAME, plan)

        headers = {
            "Authorization": f"Bearer {settings.HUBSPOT_API_KEY}",
            "Content-Type": "application/json",
        }

        # 2. HTTP call with timeout — route by operation
        async with httpx.AsyncClient(timeout=10.0) as client:
            if operation == "list_accounts":
                params: dict[str, Any] = {"limit": limit}
                if filters:
                    params.update(filters)
                resp = await client.get(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/companies",
                    headers=headers,
                    params=params,
                )

            elif operation == "get_account":
                if not record_id:
                    raise ValueError("record_id is required for get_account operation")
                resp = await client.get(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/companies/{record_id}",
                    headers=headers,
                )

            elif operation == "list_contacts":
                params = {"limit": limit}
                if filters:
                    params.update(filters)
                resp = await client.get(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/contacts",
                    headers=headers,
                    params=params,
                )

            elif operation == "get_deals":
                params = {"limit": limit}
                if filters:
                    params.update(filters)
                resp = await client.get(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/deals",
                    headers=headers,
                    params=params,
                )

            elif operation == "get_deal_history":
                if not record_id:
                    raise ValueError("record_id is required for get_deal_history operation")
                resp = await client.get(
                    f"{HUBSPOT_API_BASE}/crm/v3/objects/deals/{record_id}",
                    headers=headers,
                    params={"propertiesWithHistory": "dealstage,amount,closedate"},
                )

            else:
                raise ValueError(f"Unknown CRM reader operation: {operation}")

        # 3. Specific error handling
        if resp.status_code == 429:
            raise CRMReaderError(
                f"Rate limited by HubSpot API for workspace {workspace_id}"
            )
        if resp.status_code == 401:
            raise CRMAuthError("Invalid HubSpot API credentials")
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()

        log.info(
            "crm_reader.complete",
            operation=operation,
            workspace_id=workspace_id,
        )

        return data
