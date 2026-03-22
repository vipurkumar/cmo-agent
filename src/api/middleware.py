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
# API Key Auth Middleware
# ---------------------------------------------------------------------------

import hashlib as _hashlib
import uuid as _uuid

from src.db.queries import async_session_factory, get_api_key_by_hash, get_workspace, update_api_key_last_used

# Paths that don't require API key auth
_AUTH_EXEMPT_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})
_AUTH_EXEMPT_PREFIXES = ("/webhooks/", "/demo")


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer API key on all non-exempt endpoints.

    Sets request.state.workspace_id and request.state.workspace_plan.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip auth for exempt paths
        if path in _AUTH_EXEMPT_PATHS or any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
            return await call_next(request)

        # Check for admin key on workspace creation
        if path == "/api/v1/workspaces" and request.method == "POST":
            admin_key = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if admin_key and admin_key == settings.ADMIN_API_KEY:
                request.state.workspace_id = "__admin__"
                request.state.workspace_plan = "enterprise"
                return await call_next(request)

        # Extract Bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer cmo_"):
            return JSONResponse(
                status_code=401,
                content={
                    "error_code": "AUTH_MISSING_KEY",
                    "message": "Missing or invalid API key. Use Authorization: Bearer cmo_...",
                },
            )

        raw_key = auth_header.removeprefix("Bearer ").strip()
        key_hash = _hashlib.sha256(raw_key.encode()).hexdigest()

        # Look up in DB
        try:
            async with async_session_factory() as session:
                api_key = await get_api_key_by_hash(session, key_hash)
                if not api_key:
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error_code": "AUTH_INVALID_KEY",
                            "message": "Invalid or deactivated API key.",
                        },
                    )

                workspace = await get_workspace(session, api_key.workspace_id)
                plan = workspace.plan if workspace else "free"

                # Update last_used_at (fire-and-forget, don't block the request)
                await update_api_key_last_used(session, api_key.id)
                await session.commit()
        except Exception as exc:
            log.error("auth.db_error", error=str(exc))
            return JSONResponse(
                status_code=503,
                content={
                    "error_code": "AUTH_SERVICE_UNAVAILABLE",
                    "message": "Authentication service temporarily unavailable.",
                },
            )

        request.state.workspace_id = api_key.workspace_id
        request.state.workspace_plan = plan
        return await call_next(request)


# ---------------------------------------------------------------------------
# Request ID Middleware
# ---------------------------------------------------------------------------


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generates a unique request ID for every request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(_uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


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
