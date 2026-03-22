"""Prometheus metrics middleware for FastAPI."""

from __future__ import annotations

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.observability.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Records HTTP request count and duration as Prometheus metrics."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip metrics endpoint itself to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        # Normalize path to avoid cardinality explosion
        endpoint = self._normalize_path(request.url.path)

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        status = str(response.status_code)
        HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code=status).inc()
        HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

        return response

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize path to reduce cardinality (replace UUIDs with :id)."""
        import re
        # Replace UUID-like segments
        normalized = re.sub(
            r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "/:id",
            path,
        )
        # Replace any remaining long hex/alphanumeric IDs
        normalized = re.sub(r"/[a-zA-Z0-9_-]{20,}", "/:id", normalized)
        return normalized
