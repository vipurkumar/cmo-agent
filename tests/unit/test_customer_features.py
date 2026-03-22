"""Tests for customer-facing features in CMO Agent.

Covers:
  - ApiKeyAuthMiddleware (auth enforcement, exempt paths, admin key)
  - RequestIdMiddleware (X-Request-Id header, UUID format)
  - Health endpoint (status, services, version)
  - Structured error responses (404, 422)
  - Pagination on GET /campaigns
  - Export endpoints (briefs, scores — JSON and CSV)
  - Workspace provisioning (create workspace, create/delete API keys)

Uses FastAPI TestClient with mocked DB, Redis, and external services.
"""

from __future__ import annotations

import hashlib
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORKSPACE_ID = "ws-001"
VALID_RAW_KEY = "cmo_test_key_abc123"
VALID_KEY_HASH = hashlib.sha256(VALID_RAW_KEY.encode()).hexdigest()
ADMIN_KEY = "admin-secret-key-for-tests"


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------


def _make_mock_api_key(
    workspace_id: str = WORKSPACE_ID,
    key_id: str = "key-001",
    is_active: bool = True,
):
    api_key = MagicMock()
    api_key.id = key_id
    api_key.workspace_id = workspace_id
    api_key.is_active = is_active
    api_key.name = "default"
    return api_key


def _make_mock_workspace(
    workspace_id: str = WORKSPACE_ID,
    name: str = "Test Workspace",
    plan: str = "pro",
):
    workspace = MagicMock()
    workspace.id = workspace_id
    workspace.name = name
    workspace.plan = plan
    return workspace


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_settings():
    """Settings mock with all required attributes for middleware and routes."""
    fake = MagicMock()
    fake.CLAUDE_MODEL = "claude-sonnet-4-6"
    fake.CLAUDE_HAIKU_MODEL = "claude-haiku-4-5-20251001"
    fake.ANTHROPIC_API_KEY = "test-anthropic-key"
    fake.DATABASE_URL = "postgresql+asyncpg://localhost:6432/cmo_test"
    fake.REDIS_URL = "redis://localhost:6379/15"
    fake.REDIS_KEY_PREFIX = "cmo_test:"
    fake.CLICKHOUSE_URL = "clickhouse://localhost:9000/cmo_test"
    fake.HMAC_SECRET = "test-hmac-secret"
    fake.N8N_WEBHOOK_BASE_URL = "http://localhost:5678/webhook"
    fake.MAX_ACCOUNTS_PER_BATCH = 20
    fake.SEQUENCE_MAX_STAGES = 3
    fake.HOST = "0.0.0.0"
    fake.PORT = 8000
    fake.LOG_LEVEL = "debug"
    fake.DEMO_MODE = False
    fake.ADMIN_API_KEY = ADMIN_KEY
    fake.CORS_ALLOWED_ORIGINS = ["*"]
    return fake


@contextmanager
def _patched_auth(mock_settings, api_key_record=None, workspace_record=None):
    """Context manager that patches middleware DB lookups for API key auth.

    If *api_key_record* is ``None``, ``get_api_key_by_hash`` returns ``None``
    (simulating an invalid key).
    """
    mock_session_ctx = AsyncMock()
    mock_session = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_session.commit = AsyncMock()

    with (
        patch("src.api.middleware.settings", mock_settings),
        patch("src.api.main.settings", mock_settings),
        patch("src.api.middleware.async_session_factory", return_value=mock_session_ctx),
        patch(
            "src.api.middleware.get_api_key_by_hash",
            new_callable=AsyncMock,
            return_value=api_key_record,
        ),
        patch(
            "src.api.middleware.get_workspace",
            new_callable=AsyncMock,
            return_value=workspace_record,
        ),
        patch("src.api.middleware.update_api_key_last_used", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture()
def mock_db_session():
    """AsyncMock session returned by the get_session dependency."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture()
def authed_client(mock_settings, mock_db_session):
    """TestClient pre-authenticated with a valid API key.

    All middleware DB calls are mocked so a ``Bearer cmo_...`` key is accepted.
    """
    from src.api.deps import get_session
    from src.api.main import app

    async def override_get_session():
        yield mock_db_session

    app.dependency_overrides[get_session] = override_get_session

    api_key_record = _make_mock_api_key()
    workspace_record = _make_mock_workspace()

    with _patched_auth(mock_settings, api_key_record, workspace_record):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def unauthed_client(mock_settings, mock_db_session):
    """TestClient with NO valid auth — for testing auth rejection."""
    from src.api.deps import get_session
    from src.api.main import app

    async def override_get_session():
        yield mock_db_session

    app.dependency_overrides[get_session] = override_get_session

    with (
        patch("src.api.middleware.settings", mock_settings),
        patch("src.api.main.settings", mock_settings),
    ):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    app.dependency_overrides.clear()


def _auth_headers(raw_key: str = VALID_RAW_KEY) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


# ===========================================================================
# 1. ApiKeyAuthMiddleware tests
# ===========================================================================


class TestApiKeyAuthMiddleware:
    """Validates API key authentication enforcement."""

    def test_missing_auth_header_returns_401(self, unauthed_client):
        """Request without Authorization header returns 401 AUTH_MISSING_KEY."""
        resp = unauthed_client.get("/campaigns")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error_code"] == "AUTH_MISSING_KEY"

    def test_invalid_key_returns_401(self, mock_settings, mock_db_session):
        """Request with unknown key returns 401 AUTH_INVALID_KEY."""
        from src.api.deps import get_session
        from src.api.main import app

        async def override_get_session():
            yield mock_db_session

        app.dependency_overrides[get_session] = override_get_session

        # api_key_record=None simulates key not found in DB
        with _patched_auth(mock_settings, api_key_record=None, workspace_record=None):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get(
                    "/campaigns",
                    headers={"Authorization": "Bearer cmo_invalid_key"},
                )

        app.dependency_overrides.clear()
        assert resp.status_code == 401
        data = resp.json()
        assert data["error_code"] == "AUTH_INVALID_KEY"

    def test_valid_key_sets_workspace_id(self, authed_client):
        """Valid API key sets workspace_id on request.state (verified via successful request)."""
        # A valid key should pass through middleware and reach the route.
        # GET /campaigns requires workspace_id — if middleware sets it, route works.
        with patch(
            "src.api.main.list_campaigns",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = authed_client.get("/campaigns", headers=_auth_headers())
        assert resp.status_code == 200

    def test_health_is_exempt_from_auth(self, unauthed_client):
        """GET /health does not require an API key."""
        with (
            patch("src.api.main.async_session_factory") as mock_sf,
            patch("redis.asyncio.Redis.from_url") as mock_redis_cls,
        ):
            # Mock DB check
            mock_session_ctx = AsyncMock()
            mock_session = AsyncMock()
            mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = mock_session_ctx

            # Mock Redis check
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_redis_cls.return_value = mock_redis

            resp = unauthed_client.get("/health")
        assert resp.status_code == 200

    def test_docs_endpoint_is_exempt_from_auth(self, unauthed_client):
        """GET /docs does not require an API key."""
        resp = unauthed_client.get("/docs")
        assert resp.status_code == 200

    def test_webhooks_are_exempt_from_auth(self, unauthed_client):
        """Webhook endpoints skip API key auth (HMAC is used instead)."""
        # We just need to verify middleware doesn't reject with AUTH_MISSING_KEY.
        # The HMAC middleware will reject without a signature, but that's a
        # separate concern — the error should NOT be AUTH_MISSING_KEY.
        resp = unauthed_client.post(
            "/webhooks/n8n",
            json={
                "event_type": "test",
                "payload": {},
                "workspace_id": WORKSPACE_ID,
            },
        )
        # Should get HMAC rejection (401) but NOT AUTH_MISSING_KEY
        assert resp.status_code == 401
        data = resp.json()
        assert data.get("error_code") != "AUTH_MISSING_KEY"

    def test_demo_endpoints_are_exempt_from_auth(self, unauthed_client):
        """Paths starting with /demo skip API key auth."""
        # Demo mode is off, so /demo will 404 or 405. But the auth middleware
        # should not block it — we verify no AUTH_MISSING_KEY error.
        resp = unauthed_client.get("/demo")
        # 404 or 405 is acceptable — just not 401 AUTH_MISSING_KEY
        if resp.status_code == 401:
            data = resp.json()
            assert data.get("error_code") != "AUTH_MISSING_KEY"

    def test_admin_key_allows_workspace_creation(self, mock_settings, mock_db_session):
        """POST /api/v1/workspaces with admin key succeeds."""
        from src.api.deps import get_session
        from src.api.main import app

        async def override_get_session():
            yield mock_db_session

        app.dependency_overrides[get_session] = override_get_session

        mock_workspace = _make_mock_workspace()
        mock_api_key_record = _make_mock_api_key()
        raw_key = "cmo_new_workspace_key"

        with (
            patch("src.api.middleware.settings", mock_settings),
            patch("src.api.main.settings", mock_settings),
            patch(
                "src.api.main.create_workspace",
                new_callable=AsyncMock,
                return_value=mock_workspace,
            ),
            patch(
                "src.api.main.create_api_key",
                new_callable=AsyncMock,
                return_value=(mock_api_key_record, raw_key),
            ),
        ):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post(
                    "/api/v1/workspaces",
                    json={"name": "New Workspace", "plan": "pro"},
                    headers={"Authorization": f"Bearer {ADMIN_KEY}"},
                )

        app.dependency_overrides.clear()
        assert resp.status_code == 201
        data = resp.json()
        assert data["workspace_id"] == WORKSPACE_ID
        assert data["api_key"] == raw_key


# ===========================================================================
# 2. RequestIdMiddleware tests
# ===========================================================================


class TestRequestIdMiddleware:
    """Validates that every response includes a unique request ID."""

    def test_response_includes_request_id_header(self, unauthed_client):
        """Every response includes an X-Request-Id header."""
        with (
            patch("src.api.main.async_session_factory") as mock_sf,
            patch("redis.asyncio.Redis.from_url") as mock_redis_cls,
        ):
            mock_session_ctx = AsyncMock()
            mock_session = AsyncMock()
            mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = mock_session_ctx

            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_redis_cls.return_value = mock_redis

            resp = unauthed_client.get("/health")
        assert "X-Request-Id" in resp.headers

    def test_request_id_is_valid_uuid(self, unauthed_client):
        """The X-Request-Id header value is a valid UUID."""
        with (
            patch("src.api.main.async_session_factory") as mock_sf,
            patch("redis.asyncio.Redis.from_url") as mock_redis_cls,
        ):
            mock_session_ctx = AsyncMock()
            mock_session = AsyncMock()
            mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = mock_session_ctx

            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_redis_cls.return_value = mock_redis

            resp = unauthed_client.get("/health")
        request_id = resp.headers["X-Request-Id"]
        # Should not raise ValueError
        parsed = uuid.UUID(request_id)
        assert str(parsed) == request_id


# ===========================================================================
# 3. Health endpoint tests
# ===========================================================================


class TestHealthEndpoint:
    """Validates /health returns proper structure when services are up."""

    def _mock_health_deps(self):
        """Return context manager that mocks DB, Redis, and ClickHouse for health."""
        @contextmanager
        def _ctx():
            with (
                patch("src.api.main.async_session_factory") as mock_sf,
                patch("redis.asyncio.Redis.from_url") as mock_redis_cls,
                patch("src.api.main.settings") as mock_settings_local,
            ):
                # DB
                mock_session_ctx = AsyncMock()
                mock_session = AsyncMock()
                mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_sf.return_value = mock_session_ctx

                # Redis
                mock_redis = AsyncMock()
                mock_redis.ping = AsyncMock()
                mock_redis.aclose = AsyncMock()
                mock_redis_cls.return_value = mock_redis

                # ClickHouse — patch at module level
                mock_settings_local.REDIS_URL = "redis://localhost:6379/15"
                mock_settings_local.CLICKHOUSE_URL = "clickhouse://localhost:9000/cmo_test"

                yield

        return _ctx()

    def test_health_returns_200_with_status_ok(self, unauthed_client):
        """GET /health returns 200 with status 'ok' when DB and Redis are up."""
        with self._mock_health_deps():
            resp = unauthed_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_returns_services_dict(self, unauthed_client):
        """Response includes services dict with database, redis, clickhouse keys."""
        with self._mock_health_deps():
            resp = unauthed_client.get("/health")
        data = resp.json()
        services = data["services"]
        assert "database" in services
        assert "redis" in services
        assert "clickhouse" in services

    def test_health_returns_version(self, unauthed_client):
        """Response includes a version string."""
        with self._mock_health_deps():
            resp = unauthed_client.get("/health")
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert data["version"] == "0.1.0"


# ===========================================================================
# 4. Structured error tests
# ===========================================================================


class TestStructuredErrors:
    """Validates that error responses follow the structured error format."""

    def test_404_returns_structured_error(self, authed_client):
        """404 returns {error_code: 'NOT_FOUND', message: ...}."""
        with patch(
            "src.api.main.get_campaign",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = authed_client.get(
                "/campaigns/nonexistent-id",
                headers=_auth_headers(),
            )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error_code"] == "NOT_FOUND"
        assert "message" in data

    def test_422_validation_error_returns_structured_error(self, authed_client):
        """422 validation error returns {error_code: 'VALIDATION_ERROR', details: ...}."""
        # POST /campaigns with empty name (violates min_length=1)
        resp = authed_client.post(
            "/campaigns",
            json={"name": ""},
            headers=_auth_headers(),
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert "details" in data


# ===========================================================================
# 5. Pagination tests
# ===========================================================================


class TestPagination:
    """Validates paginated responses from GET /campaigns."""

    def test_campaigns_returns_paginated_response(self, authed_client):
        """GET /campaigns returns items, total, page, page_size, total_pages."""
        fake_campaign = MagicMock()
        fake_campaign.id = "camp-001"
        fake_campaign.name = "Test Campaign"
        fake_campaign.created_at = datetime(2026, 1, 15, tzinfo=timezone.utc)

        with patch(
            "src.api.main.list_campaigns",
            new_callable=AsyncMock,
            return_value=([fake_campaign], 1),
        ):
            resp = authed_client.get("/campaigns", headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert data["total"] == 1
        assert data["page"] == 1
        assert len(data["items"]) == 1

    def test_page_size_capped_at_100(self, authed_client):
        """Requesting page_size > 100 is capped to 100."""
        with patch(
            "src.api.main.list_campaigns",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_list:
            resp = authed_client.get(
                "/campaigns?page_size=500",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["page_size"] == 100

    def test_pagination_defaults(self, authed_client):
        """Default page=1 and page_size=20."""
        with patch(
            "src.api.main.list_campaigns",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = authed_client.get("/campaigns", headers=_auth_headers())

        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_total_pages_calculation(self, authed_client):
        """total_pages is ceil(total / page_size)."""
        with patch(
            "src.api.main.list_campaigns",
            new_callable=AsyncMock,
            return_value=([], 45),
        ):
            resp = authed_client.get(
                "/campaigns?page_size=20",
                headers=_auth_headers(),
            )

        data = resp.json()
        assert data["total_pages"] == 3  # ceil(45/20) = 3


# ===========================================================================
# 6. Export endpoint tests
# ===========================================================================


class TestExportEndpoints:
    """Validates /api/v1/export/briefs and /api/v1/export/scores."""

    def _make_brief_record(self):
        record = MagicMock()
        record.id = "brief-001"
        record.account_id = "acct-001"
        record.action_type = "outbound"
        record.overall_score = 85
        record.confidence_score = 0.9
        record.version = 1
        record.brief_json = {"summary": "Test brief"}
        record.generated_at = datetime(2026, 1, 15, tzinfo=timezone.utc)
        record.workspace_id = WORKSPACE_ID
        return record

    def _make_score_record(self):
        record = MagicMock()
        record.account_id = "acct-001"
        record.icp_fit_score = 80
        record.pain_fit_score = 70
        record.timing_score = 60
        record.overall_priority_score = 75
        record.confidence_score = 0.85
        record.is_disqualified = False
        record.scored_at = datetime(2026, 1, 15, tzinfo=timezone.utc)
        record.workspace_id = WORKSPACE_ID
        return record

    def test_export_briefs_json_returns_list(self, authed_client, mock_db_session):
        """GET /api/v1/export/briefs?format=json returns a JSON list."""
        brief = self._make_brief_record()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [brief]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = authed_client.get(
            "/api/v1/export/briefs?format=json",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["brief_id"] == "brief-001"

    def test_export_briefs_csv_returns_csv_with_header(self, authed_client, mock_db_session):
        """GET /api/v1/export/briefs?format=csv returns CSV with Content-Disposition."""
        brief = self._make_brief_record()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [brief]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = authed_client.get(
            "/api/v1/export/briefs?format=csv",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["Content-Disposition"]
        assert resp.headers["content-type"].startswith("text/csv")
        # Verify CSV has header row
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 2  # header + at least 1 data row
        assert "brief_id" in lines[0]

    def test_export_scores_json_returns_list(self, authed_client, mock_db_session):
        """GET /api/v1/export/scores returns a JSON list."""
        score = self._make_score_record()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [score]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = authed_client.get(
            "/api/v1/export/scores?format=json",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["account_id"] == "acct-001"
        assert data[0]["icp_fit_score"] == 80


# ===========================================================================
# 7. Workspace provisioning tests
# ===========================================================================


class TestWorkspaceProvisioning:
    """Validates workspace and API key management endpoints."""

    def test_create_workspace_returns_201_and_api_key(self, mock_settings, mock_db_session):
        """POST /api/v1/workspaces creates workspace and returns API key."""
        from src.api.deps import get_session
        from src.api.main import app

        async def override_get_session():
            yield mock_db_session

        app.dependency_overrides[get_session] = override_get_session

        mock_workspace = _make_mock_workspace()
        mock_api_key_record = _make_mock_api_key()
        raw_key = "cmo_brand_new_key"

        with (
            patch("src.api.middleware.settings", mock_settings),
            patch("src.api.main.settings", mock_settings),
            patch(
                "src.api.main.create_workspace",
                new_callable=AsyncMock,
                return_value=mock_workspace,
            ),
            patch(
                "src.api.main.create_api_key",
                new_callable=AsyncMock,
                return_value=(mock_api_key_record, raw_key),
            ),
        ):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.post(
                    "/api/v1/workspaces",
                    json={"name": "My Workspace", "plan": "pro"},
                    headers={"Authorization": f"Bearer {ADMIN_KEY}"},
                )

        app.dependency_overrides.clear()

        assert resp.status_code == 201
        data = resp.json()
        assert data["workspace_id"] == WORKSPACE_ID
        assert data["name"] == "Test Workspace"
        assert data["plan"] == "pro"
        assert data["api_key"] == raw_key

    def test_create_additional_api_key(self, authed_client, mock_db_session):
        """POST /api/v1/workspaces/{id}/api-keys creates an additional key."""
        mock_workspace = _make_mock_workspace()
        mock_api_key_record = _make_mock_api_key(key_id="key-002")
        mock_api_key_record.name = "secondary"
        raw_key = "cmo_secondary_key"

        with (
            patch(
                "src.api.main.get_workspace",
                new_callable=AsyncMock,
                return_value=mock_workspace,
            ),
            patch(
                "src.api.main.create_api_key",
                new_callable=AsyncMock,
                return_value=(mock_api_key_record, raw_key),
            ),
        ):
            resp = authed_client.post(
                f"/api/v1/workspaces/{WORKSPACE_ID}/api-keys",
                json={"name": "secondary"},
                headers=_auth_headers(),
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["key_id"] == "key-002"
        assert data["api_key"] == raw_key
        assert data["name"] == "secondary"

    def test_delete_api_key_deactivates(self, authed_client, mock_db_session):
        """DELETE /api/v1/workspaces/{id}/api-keys/{key_id} deactivates the key."""
        with patch(
            "src.api.main.deactivate_api_key",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = authed_client.delete(
                f"/api/v1/workspaces/{WORKSPACE_ID}/api-keys/key-001",
                headers=_auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deactivated"

    def test_delete_nonexistent_api_key_returns_404(self, authed_client, mock_db_session):
        """DELETE /api/v1/workspaces/{id}/api-keys/{key_id} returns 404 when not found."""
        with patch(
            "src.api.main.deactivate_api_key",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = authed_client.delete(
                f"/api/v1/workspaces/{WORKSPACE_ID}/api-keys/key-nonexistent",
                headers=_auth_headers(),
            )

        assert resp.status_code == 404

    def test_cannot_create_key_for_other_workspace(self, authed_client, mock_db_session):
        """POST /api/v1/workspaces/{other_id}/api-keys returns 403."""
        resp = authed_client.post(
            "/api/v1/workspaces/ws-other-999/api-keys",
            json={"name": "sneaky"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 403

    def test_cannot_delete_key_for_other_workspace(self, authed_client, mock_db_session):
        """DELETE /api/v1/workspaces/{other_id}/api-keys/{key_id} returns 403."""
        resp = authed_client.delete(
            "/api/v1/workspaces/ws-other-999/api-keys/key-001",
            headers=_auth_headers(),
        )
        assert resp.status_code == 403
