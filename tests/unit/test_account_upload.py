"""Tests for account upload (no-CRM) flow + data_ingester modifications."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.state import Account, Contact, QualificationState


# ---------------------------------------------------------------------------
# data_ingester — direct upload mode (no CRM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_data_ingester_direct_upload_skips_crm(mock_settings):
    """When raw_accounts contain full data (company_name), CRM should not be called."""
    mock_settings.USE_APOLLO_ENRICHMENT = False
    mock_settings.USE_CLAY_ENRICHMENT = False

    with patch("src.agent.nodes.data_ingester.settings", mock_settings), \
         patch("src.agent.nodes.data_ingester._rate_limiter", MagicMock()):

        from src.agent.nodes.data_ingester import data_ingester

        state: QualificationState = {
            "thread_id": "test-thread",
            "workspace_id": "ws-test-001",
            "raw_accounts": [
                {
                    "id": "acct-1",
                    "company_name": "TestCo",
                    "domain": "testco.com",
                    "industry": "SaaS",
                    "employee_count": 100,
                    "contacts": [
                        {
                            "id": "ct-1",
                            "email": "alice@testco.com",
                            "first_name": "Alice",
                            "last_name": "Smith",
                            "role": "VP Sales",
                        }
                    ],
                },
                {
                    "id": "acct-2",
                    "company_name": "BigCo",
                    "domain": "bigco.io",
                },
            ],
        }

        result = await data_ingester(state)

        assert len(result["accounts"]) == 2
        assert result["accounts"][0].company_name == "TestCo"
        assert result["accounts"][0].domain == "testco.com"
        assert result["accounts"][1].company_name == "BigCo"

        # Direct upload should have created a contact
        assert len(result["contacts"]) == 1
        assert result["contacts"][0].email == "alice@testco.com"


@pytest.mark.asyncio
async def test_data_ingester_direct_upload_with_apollo(mock_settings):
    """Apollo enrichment should still work on directly uploaded accounts."""
    mock_settings.USE_APOLLO_ENRICHMENT = True
    mock_settings.USE_CLAY_ENRICHMENT = False

    mock_apollo = AsyncMock()
    mock_apollo.enrich_organization = AsyncMock(return_value={
        "industry": "FinTech",
        "employee_count": 500,
        "technologies": ["Python", "AWS"],
    })
    mock_apollo.search_contacts = AsyncMock(return_value=[
        {
            "id": "apollo-ct-1",
            "email": "bob@testco.com",
            "first_name": "Bob",
            "last_name": "Jones",
            "role": "CTO",
        }
    ])

    with patch("src.agent.nodes.data_ingester.settings", mock_settings), \
         patch("src.agent.nodes.data_ingester._rate_limiter", MagicMock()), \
         patch("src.agent.nodes.data_ingester._get_apollo_adapter", return_value=mock_apollo):

        from src.agent.nodes.data_ingester import data_ingester

        state: QualificationState = {
            "thread_id": "test-thread",
            "workspace_id": "ws-test-001",
            "raw_accounts": [
                {
                    "id": "acct-1",
                    "company_name": "TestCo",
                    "domain": "testco.com",
                },
            ],
        }

        result = await data_ingester(state)

        assert len(result["accounts"]) == 1
        # Apollo should have filled in the industry
        assert result["accounts"][0].industry == "FinTech"
        # Apollo should have discovered contacts
        assert len(result["contacts"]) >= 1
        emails = [c.email for c in result["contacts"]]
        assert "bob@testco.com" in emails


@pytest.mark.asyncio
async def test_data_ingester_clay_enrichment(mock_settings):
    """Clay enrichment should add metadata when enabled."""
    mock_settings.USE_APOLLO_ENRICHMENT = False
    mock_settings.USE_CLAY_ENRICHMENT = True
    mock_settings.CLAY_API_KEY = "test-clay-key"

    mock_clay = AsyncMock()
    mock_clay.run = AsyncMock(return_value={
        "technologies": ["Salesforce", "HubSpot"],
        "intent_signals": ["hiring_sales"],
    })

    with patch("src.agent.nodes.data_ingester.settings", mock_settings), \
         patch("src.agent.nodes.data_ingester._rate_limiter", MagicMock()), \
         patch("src.agent.nodes.data_ingester._get_clay_tool", return_value=mock_clay):

        from src.agent.nodes.data_ingester import data_ingester

        state: QualificationState = {
            "thread_id": "test-thread",
            "workspace_id": "ws-test-001",
            "raw_accounts": [
                {
                    "id": "acct-1",
                    "company_name": "TestCo",
                    "domain": "testco.com",
                },
            ],
        }

        result = await data_ingester(state)

        assert len(result["accounts"]) == 1
        assert "clay_enrichment" in result["accounts"][0].metadata


@pytest.mark.asyncio
async def test_data_ingester_clay_failure_graceful(mock_settings):
    """Pipeline should continue when Clay enrichment fails."""
    mock_settings.USE_APOLLO_ENRICHMENT = False
    mock_settings.USE_CLAY_ENRICHMENT = True
    mock_settings.CLAY_API_KEY = "test-clay-key"

    mock_clay = AsyncMock()
    mock_clay.run = AsyncMock(side_effect=Exception("Clay API error"))

    with patch("src.agent.nodes.data_ingester.settings", mock_settings), \
         patch("src.agent.nodes.data_ingester._rate_limiter", MagicMock()), \
         patch("src.agent.nodes.data_ingester._get_clay_tool", return_value=mock_clay):

        from src.agent.nodes.data_ingester import data_ingester

        state: QualificationState = {
            "thread_id": "test-thread",
            "workspace_id": "ws-test-001",
            "raw_accounts": [
                {
                    "id": "acct-1",
                    "company_name": "TestCo",
                    "domain": "testco.com",
                },
            ],
        }

        result = await data_ingester(state)

        # Should still complete with accounts
        assert len(result["accounts"]) == 1
        assert result["accounts"][0].company_name == "TestCo"


@pytest.mark.asyncio
async def test_data_ingester_no_accounts():
    """Should return error when no accounts provided."""
    with patch("src.agent.nodes.data_ingester._rate_limiter", MagicMock()):

        from src.agent.nodes.data_ingester import data_ingester

        state: QualificationState = {
            "thread_id": "test-thread",
            "workspace_id": "ws-test-001",
            "raw_accounts": [],
        }

        result = await data_ingester(state)

        assert result["accounts"] == []
        assert "error" in result


# ---------------------------------------------------------------------------
# _has_full_account_data helper
# ---------------------------------------------------------------------------


def test_has_full_account_data_true():
    from src.agent.nodes.data_ingester import _has_full_account_data

    assert _has_full_account_data([{"company_name": "TestCo"}]) is True


def test_has_full_account_data_false_ids_only():
    from src.agent.nodes.data_ingester import _has_full_account_data

    assert _has_full_account_data([{"id": "acct-1"}]) is False


def test_has_full_account_data_false_empty():
    from src.agent.nodes.data_ingester import _has_full_account_data

    assert _has_full_account_data([]) is False
