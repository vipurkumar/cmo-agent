"""Tests for src/api/main.py — FastAPI routes.

Uses FastAPI TestClient (sync wrapper) with dependency overrides
so no real DB, Redis, or queue connections are needed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORKSPACE_ID = "ws-test-001"


def _hmac_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _patch_settings(mock_settings):
    """Ensure settings are patched for all API tests."""
    # Also patch the settings import inside middleware
    with (
        patch("src.api.middleware.settings", mock_settings),
        patch("src.api.main.settings", mock_settings),
    ):
        yield mock_settings


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
def client(_patch_settings, mock_db_session):
    """TestClient with all external dependencies mocked out."""
    from src.api.main import app, get_session

    # Override the DB session dependency
    async def override_get_session():
        yield mock_db_session

    app.dependency_overrides[get_session] = override_get_session

    # We need to disable HMAC middleware for non-webhook tests.
    # For webhook tests, we'll provide a valid signature.
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------


class TestCampaignEndpoints:
    def test_create_campaign_returns_201(self, client, mock_db_session, _patch_settings):
        """POST /campaigns creates a campaign and returns 201."""
        fake_campaign = MagicMock()
        fake_campaign.id = "camp-new-001"
        fake_campaign.name = "Q1 Outbound"
        fake_campaign.created_at = datetime(2026, 1, 15, tzinfo=timezone.utc)

        with patch("src.api.main.create_campaign", new_callable=AsyncMock, return_value=fake_campaign):
            resp = client.post(
                "/campaigns",
                json={"name": "Q1 Outbound", "icp_criteria": {"industry": "SaaS"}},
                headers={"X-Workspace-Id": WORKSPACE_ID},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "camp-new-001"
        assert data["name"] == "Q1 Outbound"
        assert data["status"] == "draft"

    def test_create_campaign_requires_workspace_id(self, client):
        """POST /campaigns without X-Workspace-Id returns 400."""
        resp = client.post(
            "/campaigns",
            json={"name": "No Workspace"},
        )
        assert resp.status_code == 400

    def test_list_campaigns_returns_200(self, client, _patch_settings):
        """GET /campaigns returns a list of campaigns."""
        fake_campaign = MagicMock()
        fake_campaign.id = "camp-001"
        fake_campaign.name = "Test Campaign"
        fake_campaign.created_at = datetime(2026, 1, 15, tzinfo=timezone.utc)

        with patch("src.api.main.list_campaigns", new_callable=AsyncMock, return_value=[fake_campaign]):
            resp = client.get(
                "/campaigns",
                headers={"X-Workspace-Id": WORKSPACE_ID},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "camp-001"

    def test_list_campaigns_requires_workspace_id(self, client):
        """GET /campaigns without X-Workspace-Id returns 400."""
        resp = client.get("/campaigns")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


class TestWebhookEndpoints:
    def test_n8n_webhook_routes_correctly(self, client, _patch_settings):
        """POST /webhooks/n8n enqueues the event via enqueue_by_event."""
        body = {
            "event_type": "approval_response",
            "payload": {"thread_id": "t-001", "approved": True},
            "workspace_id": WORKSPACE_ID,
        }
        body_bytes = json.dumps(body).encode()
        signature = _hmac_signature(body_bytes, _patch_settings.HMAC_SECRET)

        with patch("src.api.main.enqueue_by_event", new_callable=AsyncMock, return_value="job-001"):
            resp = client.post(
                "/webhooks/n8n",
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": signature,
                    "X-Workspace-Id": WORKSPACE_ID,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job-001"
        assert data["status"] == "accepted"

    def test_webhook_requires_hmac_signature(self, client, _patch_settings):
        """POST /webhooks/n8n without signature returns 401."""
        body = {
            "event_type": "approval_response",
            "payload": {},
            "workspace_id": WORKSPACE_ID,
        }

        resp = client.post(
            "/webhooks/n8n",
            json=body,
            headers={"X-Workspace-Id": WORKSPACE_ID},
        )

        assert resp.status_code == 401

    def test_webhook_invalid_hmac_returns_401(self, client, _patch_settings):
        """POST /webhooks/n8n with wrong signature returns 401."""
        body = {
            "event_type": "approval_response",
            "payload": {},
            "workspace_id": WORKSPACE_ID,
        }

        resp = client.post(
            "/webhooks/n8n",
            json=body,
            headers={
                "X-Webhook-Signature": "invalid-signature",
                "X-Workspace-Id": WORKSPACE_ID,
            },
        )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Workspace-ID header requirement
# ---------------------------------------------------------------------------


class TestWorkspaceIdRequirement:
    def test_campaigns_endpoint_requires_header(self, client):
        resp = client.get("/campaigns")
        assert resp.status_code == 400
        assert "X-Workspace-Id" in resp.json().get("detail", "")

    def test_create_campaign_requires_header(self, client):
        resp = client.post("/campaigns", json={"name": "Test"})
        assert resp.status_code == 400

    def test_health_does_not_require_header(self, client):
        """The /health endpoint works without a workspace ID."""
        resp = client.get("/health")
        assert resp.status_code == 200
