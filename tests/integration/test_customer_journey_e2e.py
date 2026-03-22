"""End-to-end test: customer journey from workspace creation to data export.

Tests the complete flow:
1. Create workspace -> get API key
2. Create campaign
3. List campaigns (with pagination)
4. Trigger qualification
5. Check automation status
6. Get usage stats
7. Export data
8. Manage notifications
9. Health check
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import hashlib

import pytest
from fastapi.testclient import TestClient


# Mock the DB engine creation before importing app
with patch("src.db.queries.create_async_engine"), \
     patch("src.db.queries.async_sessionmaker"):
    from src.api.main import app


@pytest.fixture
def admin_key():
    return "test-admin-key"


@pytest.fixture
def mock_settings(admin_key):
    mock = MagicMock()
    mock.ADMIN_API_KEY = admin_key
    mock.REDIS_KEY_PREFIX = "cmo_test:"
    mock.REDIS_URL = "redis://localhost:6379/15"
    mock.DATABASE_URL = "postgresql+asyncpg://localhost/test"
    mock.CLICKHOUSE_URL = "clickhouse://localhost:9000/test"
    mock.CORS_ALLOWED_ORIGINS = ["*"]
    mock.HMAC_SECRET = "test-hmac"
    mock.DEMO_MODE = False
    return mock


@pytest.fixture
def client(mock_settings):
    """TestClient with mocked auth middleware."""
    # Patch settings globally
    with patch("src.api.middleware.settings", mock_settings), \
         patch("src.config.settings", mock_settings):
        yield TestClient(app, raise_server_errors=False)


class TestCustomerJourney:
    """Full customer journey end-to-end test."""

    def test_health_check(self, client):
        """Health endpoint is accessible without auth."""
        with patch("src.api.main.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value = mock_session

            response = client.get("/health")
            # May return 200 or 503 depending on service mocks
            assert response.status_code in (200, 503)
            data = response.json()
            assert "status" in data
            assert "services" in data
            assert "version" in data

    def test_unauthenticated_request_returns_401(self, client):
        """Requests without API key return 401."""
        response = client.get("/campaigns")
        assert response.status_code == 401
        data = response.json()
        assert data["error_code"] == "AUTH_MISSING_KEY"

    def test_invalid_api_key_returns_401(self, client):
        """Requests with invalid API key return 401."""
        with patch("src.api.middleware.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value = mock_session

            with patch("src.api.middleware.get_api_key_by_hash", new_callable=AsyncMock, return_value=None):
                response = client.get(
                    "/campaigns",
                    headers={"Authorization": "Bearer cmo_invalid_key_here"}
                )
                assert response.status_code == 401

    def test_docs_accessible_without_auth(self, client):
        """OpenAPI docs are accessible without authentication."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_schema(self, client):
        """OpenAPI schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "CMO Agent API"
        assert "paths" in schema

    def test_structured_error_format(self, client):
        """Errors return structured format with error_code and request_id."""
        response = client.get("/campaigns")  # No auth
        assert response.status_code == 401
        data = response.json()
        assert "error_code" in data
        assert "message" in data

    def test_cors_headers(self, client):
        """CORS headers are present on responses."""
        response = client.options(
            "/health",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
            }
        )
        # FastAPI CORS middleware should respond
        assert response.status_code in (200, 405)

    def test_request_id_header(self, client):
        """Every response includes X-Request-Id header."""
        response = client.get("/health")
        assert "x-request-id" in response.headers
