"""HMAC auth, rate limiting, and workspace extraction middleware.

- HMACAuthMiddleware: validates X-Webhook-Signature using HMAC-SHA256
- RateLimitMiddleware: per-workspace rate limiting on API endpoints
- WorkspaceExtractor: extracts workspace_id from X-Workspace-Id header
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from src.config import settings
from src.logger import log

# ---------------------------------------------------------------------------
# HMAC Auth Middleware
# ---------------------------------------------------------------------------


class HMACAuthMiddleware(BaseHTTPMiddleware):
    """Validates X-Webhook-Signature header using HMAC-SHA256 of request body.

    Only applied to webhook endpoints (paths starting with /webhooks/).
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only validate webhook endpoints
        if not request.url.path.startswith("/webhooks/"):
            return await call_next(request)

        signature = request.headers.get("X-Webhook-Signature")
        if not signature:
            log.warning("hmac.missing_signature", path=request.url.path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing X-Webhook-Signature header"},
            )

        body = await request.body()
        expected = hmac.new(
            settings.HMAC_SECRET.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            log.warning("hmac.invalid_signature", path=request.url.path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid HMAC signature"},
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Rate Limit Middleware
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-workspace in-memory rate limiting on API endpoints.

    Uses a simple sliding-window counter. For distributed deployments,
    replace with the Redis-backed RateLimiter from src/ratelimit/bucket.py.
    """

    def __init__(self, app, requests_per_minute: int = 60) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        workspace_id = request.headers.get("X-Workspace-Id")
        if not workspace_id:
            # Non-workspace endpoints (e.g. /health) are not rate-limited
            return await call_next(request)

        now = time.time()
        window_start = now - 60.0

        # Prune old entries
        bucket = self._buckets[workspace_id]
        self._buckets[workspace_id] = [t for t in bucket if t > window_start]
        bucket = self._buckets[workspace_id]

        if len(bucket) >= self.requests_per_minute:
            retry_after = int(bucket[0] - window_start) + 1
            log.warning(
                "ratelimit.api_exceeded",
                workspace_id=workspace_id,
                path=request.url.path,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        return await call_next(request)


# ---------------------------------------------------------------------------
# Workspace Extractor Middleware
# ---------------------------------------------------------------------------


class WorkspaceExtractor(BaseHTTPMiddleware):
    """Extracts workspace_id from X-Workspace-Id header and adds it to
    ``request.state.workspace_id``.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        workspace_id = request.headers.get("X-Workspace-Id")
        request.state.workspace_id = workspace_id
        return await call_next(request)
