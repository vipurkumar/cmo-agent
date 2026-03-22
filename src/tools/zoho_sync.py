"""ZohoSyncTool — syncs data to/from Zoho CRM."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class ZohoRateLimitError(Exception):
    """Raised when Zoho returns HTTP 429."""


class ZohoAuthError(Exception):
    """Raised when Zoho returns HTTP 401 (token expired or invalid)."""


ZOHO_API_BASE = "https://www.zohoapis.com/crm/v5"
ZOHO_TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"


class ZohoSyncTool(BaseTool):
    """Syncs data to/from Zoho CRM.

    Input: record_type + data.
    Output: sync status dict.
    """

    RESOURCE_NAME = "zoho"

    def __init__(self, rate_limiter: RateLimiter) -> None:
        super().__init__(rate_limiter)
        self._access_token: str | None = None

    async def _refresh_access_token(self) -> str:
        """Obtain a fresh access token using the stored refresh token."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                ZOHO_TOKEN_URL,
                params={
                    "refresh_token": settings.ZOHO_REFRESH_TOKEN,
                    "client_id": settings.ZOHO_CLIENT_ID,
                    "client_secret": settings.ZOHO_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                },
            )

        if resp.status_code == 401:
            raise ZohoAuthError("Invalid Zoho OAuth credentials")
        resp.raise_for_status()

        data = resp.json()
        self._access_token = data["access_token"]
        return self._access_token

    async def _get_access_token(self) -> str:
        """Return a cached access token or refresh it."""
        if self._access_token is None:
            return await self._refresh_access_token()
        return self._access_token

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def run(
        self,
        record_type: str,
        workspace_id: str,
        plan: str,
        data: dict[str, Any] | None = None,
        operation: str = "upsert",
        record_id: str | None = None,
    ) -> dict[str, Any]:
        """Sync data to/from Zoho CRM.

        Parameters
        ----------
        record_type:
            Zoho module name: ``"Leads"``, ``"Contacts"``, ``"Deals"``, etc.
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace.
        data:
            Dict of field values to sync.
        operation:
            One of ``"upsert"``, ``"get"``, ``"create"``, ``"update"``.
        record_id:
            Zoho record ID (required for ``get`` and ``update``).

        Returns
        -------
        dict[str, Any]
            ``{"status": "success"|"error", "record": {...}, ...}``
        """
        log.info(
            "zoho_sync.start",
            record_type=record_type,
            operation=operation,
            workspace_id=workspace_id,
        )

        # 1. Rate limit check FIRST
        await self.rate_limiter.enforce(workspace_id, self.RESOURCE_NAME, plan)

        # 2. Obtain access token
        access_token = await self._get_access_token()

        headers = {
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "Content-Type": "application/json",
        }

        # 3. HTTP call with timeout — route by operation
        async with httpx.AsyncClient(timeout=10.0) as client:
            if operation == "get":
                if not record_id:
                    raise ValueError("record_id is required for get operation")
                resp = await client.get(
                    f"{ZOHO_API_BASE}/{record_type}/{record_id}",
                    headers=headers,
                )

            elif operation == "create":
                resp = await client.post(
                    f"{ZOHO_API_BASE}/{record_type}",
                    headers=headers,
                    json={"data": [data or {}]},
                )

            elif operation == "update":
                if not record_id:
                    raise ValueError("record_id is required for update operation")
                resp = await client.put(
                    f"{ZOHO_API_BASE}/{record_type}/{record_id}",
                    headers=headers,
                    json={"data": [data or {}]},
                )

            elif operation == "upsert":
                resp = await client.post(
                    f"{ZOHO_API_BASE}/{record_type}/upsert",
                    headers=headers,
                    json={"data": [data or {}]},
                )

            else:
                raise ValueError(f"Unknown Zoho operation: {operation}")

        # 4. Specific error handling
        if resp.status_code == 429:
            raise ZohoRateLimitError(
                f"Rate limited by Zoho API for workspace {workspace_id}"
            )
        if resp.status_code == 401:
            # Token expired — clear cache and raise so tenacity can retry
            self._access_token = None
            raise ZohoAuthError(
                "Zoho access token expired or invalid — cleared cache"
            )
        resp.raise_for_status()

        response_data = resp.json()

        result: dict[str, Any] = {
            "status": "success",
            "operation": operation,
            "record_type": record_type,
            "response": response_data,
        }

        log.info(
            "zoho_sync.complete",
            operation=operation,
            record_type=record_type,
            workspace_id=workspace_id,
        )

        return result
