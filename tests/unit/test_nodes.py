"""Tests for agent nodes: account_selector, researcher, router."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.state import (
    Account,
    Contact,
    EnrichmentResult,
    OutboundState,
    ReplyAnalysis,
)


# ===========================================================================
# account_selector
# ===========================================================================


class TestAccountSelector:
    async def test_picks_first_account_when_no_current(self, sample_state, sample_account, sample_contact):
        from src.agent.nodes.account_selector import account_selector

        state = dict(sample_state)
        state["current_account"] = None

        result = await account_selector(state)

        assert result["current_account"] == sample_account
        assert result["current_contact"] == sample_contact
        assert result["current_stage"] == 1
        assert result["should_continue"] is True

    async def test_advances_to_next_account(self, sample_state, sample_account, sample_contact):
        from src.agent.nodes.account_selector import account_selector

        second_account = Account(
            id="acct-002",
            workspace_id="ws-test-001",
            company_name="Beta Inc",
            domain="beta.io",
        )
        second_contact = Contact(
            id="contact-002",
            workspace_id="ws-test-001",
            account_id="acct-002",
            email="bob@beta.io",
            first_name="Bob",
        )

        state = dict(sample_state)
        state["accounts"] = [sample_account, second_account]
        state["contacts"] = [sample_contact, second_contact]
        state["current_account"] = sample_account  # already processed first

        result = await account_selector(state)

        assert result["current_account"] == second_account
        assert result["current_contact"] == second_contact
        assert result["current_stage"] == 1

    async def test_no_accounts_stops(self, sample_state):
        from src.agent.nodes.account_selector import account_selector

        state = dict(sample_state)
        state["accounts"] = []
        state["current_account"] = None

        result = await account_selector(state)

        assert result["should_continue"] is False

    async def test_all_accounts_processed_stops(self, sample_state, sample_account):
        from src.agent.nodes.account_selector import account_selector

        state = dict(sample_state)
        state["accounts"] = [sample_account]
        state["current_account"] = sample_account  # already at last account

        result = await account_selector(state)

        assert result["should_continue"] is False

    async def test_no_contact_for_account(self, sample_state, sample_account):
        from src.agent.nodes.account_selector import account_selector

        state = dict(sample_state)
        state["contacts"] = []  # no contacts at all
        state["current_account"] = None

        result = await account_selector(state)

        assert result["current_account"] == sample_account
        assert result["current_contact"] is None
        assert result["should_continue"] is True


# ===========================================================================
# researcher
# ===========================================================================


class TestResearcher:
    async def test_returns_enrichment_result(self, sample_state, mock_settings):
        from src.agent.nodes import researcher as researcher_mod

        mock_apollo = AsyncMock()
        mock_apollo.run = AsyncMock(return_value=[
            {"name": "Jane Doe", "title": "VP Engineering"}
        ])

        mock_news = AsyncMock()
        mock_news.run = AsyncMock(return_value=[
            {"title": "Acme raises Series B", "url": "https://news.com/acme"}
        ])

        enrichment_json = json.dumps({
            "company_summary": "Acme Corp is a growing SaaS company.",
            "recent_news": ["Acme raises Series B"],
            "pain_points": ["Scaling outbound"],
            "personalization_hooks": ["Series B momentum"],
            "technologies": ["Python", "AWS"],
        })

        with (
            patch.object(researcher_mod, "_rate_limiter", AsyncMock()),
            patch.object(researcher_mod, "_get_tools", return_value=(mock_apollo, mock_news)),
            patch("src.agent.nodes.researcher.call_claude", new_callable=AsyncMock, return_value=enrichment_json),
            patch("src.agent.nodes.researcher.settings", mock_settings),
        ):
            result = await researcher_mod.researcher(sample_state)

        assert "enrichment" in result
        enrichment = result["enrichment"]
        assert isinstance(enrichment, EnrichmentResult)
        assert enrichment.company_summary == "Acme Corp is a growing SaaS company."
        assert "Series B momentum" in enrichment.personalization_hooks

    async def test_no_current_account_returns_error(self, sample_state):
        from src.agent.nodes.researcher import researcher

        state = dict(sample_state)
        state["current_account"] = None

        result = await researcher(state)

        assert "error" in result
        assert result["error"] == "No current_account set"

    async def test_tool_error_returns_error(self, sample_state, mock_settings):
        from src.agent.nodes import researcher as researcher_mod

        mock_apollo = AsyncMock()
        mock_apollo.run = AsyncMock(side_effect=RuntimeError("Apollo API down"))

        mock_news = AsyncMock()
        mock_news.run = AsyncMock(return_value=[])

        with (
            patch.object(researcher_mod, "_rate_limiter", AsyncMock()),
            patch.object(researcher_mod, "_get_tools", return_value=(mock_apollo, mock_news)),
            patch("src.agent.nodes.researcher.settings", mock_settings),
        ):
            result = await researcher_mod.researcher(sample_state)

        assert result.get("error") is not None
        assert "Apollo API down" in result["error"]


# ===========================================================================
# router
# ===========================================================================


class TestRouter:
    async def test_positive_reply_stops(self, sample_state):
        from src.agent.nodes.router import router

        state = dict(sample_state)
        state["reply_analysis"] = ReplyAnalysis(
            intent="positive",
            confidence=0.95,
            reasoning="Prospect wants a demo.",
            suggested_action="notify_sales",
        )

        result = await router(state)

        assert result["should_continue"] is False

    async def test_unsubscribe_reply_stops(self, sample_state):
        from src.agent.nodes.router import router

        state = dict(sample_state)
        state["reply_analysis"] = ReplyAnalysis(
            intent="unsubscribe",
            confidence=0.99,
            reasoning="Prospect asked to be removed.",
            suggested_action="unsubscribe",
        )

        result = await router(state)

        assert result["should_continue"] is False

    async def test_negative_reply_stops(self, sample_state):
        from src.agent.nodes.router import router

        state = dict(sample_state)
        state["reply_analysis"] = ReplyAnalysis(
            intent="negative",
            confidence=0.85,
            reasoning="Prospect said not interested.",
            suggested_action="pause_sequence",
        )

        result = await router(state)

        assert result["should_continue"] is False

    async def test_no_reply_advances_stage(self, sample_state):
        from src.agent.nodes.router import router

        state = dict(sample_state)
        state["reply_analysis"] = None
        state["current_stage"] = 1
        state["max_stages"] = 3

        result = await router(state)

        assert result["should_continue"] is True
        assert result["current_stage"] == 2

    async def test_max_stages_exhausted_stops(self, sample_state):
        from src.agent.nodes.router import router

        state = dict(sample_state)
        state["reply_analysis"] = None
        state["current_stage"] = 3
        state["max_stages"] = 3

        result = await router(state)

        assert result["should_continue"] is False
        assert result["current_stage"] == 3

    async def test_neutral_reply_advances_stage(self, sample_state):
        from src.agent.nodes.router import router

        state = dict(sample_state)
        state["reply_analysis"] = ReplyAnalysis(
            intent="neutral",
            confidence=0.7,
            reasoning="Out-of-office reply.",
            suggested_action="send_followup",
        )
        state["current_stage"] = 1
        state["max_stages"] = 3

        result = await router(state)

        # neutral reply has no explicit handling, falls through to stage advancement
        assert result["should_continue"] is True
        assert result["current_stage"] == 2
