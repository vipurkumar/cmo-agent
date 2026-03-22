"""Outbound webhook dispatcher with retry logic.

Delivers events to customer-registered webhook URLs with:
- HMAC-SHA256 signature on every request
- Exponential backoff retries (3 attempts: 1min, 5min, 30min)
- Delivery status tracking in PostgreSQL
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx

from src.logger import log

# Retry schedule: delay after each failed attempt
RETRY_DELAYS = [60, 300, 1800]  # 1min, 5min, 30min
MAX_ATTEMPTS = 3


async def dispatch_webhook(
    url: str,
    secret: str,
    event_type: str,
    payload: dict[str, Any],
    workspace_id: str,
) -> dict[str, Any]:
    """Send a webhook with HMAC signature. Returns delivery result."""
    body = json.dumps({
        "event_type": event_type,
        "workspace_id": workspace_id,
        "payload": payload,
        "timestamp": datetime.now(UTC).isoformat(),
        "delivery_id": str(uuid4()),
    }, default=str)

    signature = hmac.new(
        secret.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": signature,
                    "X-CMO-Event": event_type,
                    "User-Agent": "CMO-Agent-Webhook/1.0",
                },
            )

        log.info(
            "webhook.delivered",
            url=url,
            event_type=event_type,
            workspace_id=workspace_id,
            status_code=response.status_code,
        )

        return {
            "status": "delivered" if response.status_code < 400 else "failed",
            "status_code": response.status_code,
            "response_body": response.text[:500],
        }

    except Exception as exc:
        log.error(
            "webhook.delivery_failed",
            url=url,
            event_type=event_type,
            workspace_id=workspace_id,
            error=str(exc),
        )
        return {
            "status": "failed",
            "status_code": None,
            "response_body": str(exc),
        }


def get_next_retry_delay(attempt: int) -> int | None:
    """Get delay in seconds for the next retry. Returns None if max attempts reached."""
    if attempt >= MAX_ATTEMPTS:
        return None
    return RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
