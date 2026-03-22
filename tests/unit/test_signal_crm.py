"""Tests for signal_detector and crm_writer nodes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.state import (
    Account,
    AccountScore,
    ActionRecommendation,
    ActionType,
    BuyingRole,
    Campaign,
    Contact,
    Evidence,
    EvidenceType,
    PainHypothesis,
    PainType,
    QualificationState,
    RankedContact,
    SellerBrief,
    Signal,
    SignalType,
    ValuePropRecommendation,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_account():
    return Account(
        id="acct-001",
        workspace_id="ws-test-001",
        company_name="Acme Corp",
        domain="acme.com",
        industry="SaaS",
        employee_count=250,
        revenue=15_000_000.0,
    )


@pytest.fixture()
def sample_campaign():
    return Campaign(
        id="camp-001",
        workspace_id="ws-test-001",
        name="Q1 SaaS Outbound",
        status="active",
        icp_criteria={"plan": "pro"},
    )


@pytest.fixture()
def sample_contact(sample_account):
    return Contact(
        id="contact-001",
        workspace_id=sample_account.workspace_id,
        account_id=sample_account.id,
        email="jane@acme.com",
        first_name="Jane",
        last_name="Doe",
        role="VP of Engineering",
    )


@pytest.fixture()
def sample_score(sample_account):
    return AccountScore(
        account_id=sample_account.id,
        workspace_id=sample_account.workspace_id,
        icp_fit_score=85,
        pain_fit_score=70,
        timing_score=60,
        overall_priority_score=75,
        fit_reasons=[
            Evidence(
                statement="SaaS target",
                evidence_type=EvidenceType.FACT,
                source="icp_scorer",
                confidence=0.9,
            )
        ],
        non_fit_reasons=[],
        confidence_score=0.8,
    )


@pytest.fixture()
def sample_brief(sample_account, sample_score):
    return SellerBrief(
        id="brief-001",
        account_id=sample_account.id,
        workspace_id=sample_account.workspace_id,
        account_snapshot="Acme is a mid-market SaaS",
        why_this_account="Strong ICP fit",
        why_now="Recent funding round",
        likely_pain_points=[
            PainHypothesis(
                pain_type=PainType.PRICING_COMPLEXITY,
                score=75,
                confidence_score=0.8,
            )
        ],
        recommended_contacts=[
            RankedContact(
                contact_id="contact-001",
                name="Jane Doe",
                title="VP Eng",
                normalized_function="Engineering",
                normalized_seniority="VP",
                relevance_score=80,
                likely_role=BuyingRole.PAIN_OWNER,
                reason_for_relevance="Owns tooling",
            )
        ],
        persona_angles=[],
        risks_and_unknowns=["Unknown billing platform"],
        recommended_action=ActionRecommendation(
            action=ActionType.PURSUE_NOW,
            explanation="Strong fit",
            confidence_score=0.85,
        ),
        scoring=sample_score,
        generated_at=datetime.now(timezone.utc),
    )


def _qual_state(account, campaign, contact, **overrides):
    state = QualificationState(
        thread_id="thread-sig-001",
        workspace_id=account.workspace_id,
        campaign=campaign,
        accounts=[account],
        current_account=account,
        contacts=[contact],
        ranked_contacts=[],
        signals=[],
        pain_hypotheses=[],
        value_props=[],
        account_score=None,
        seller_brief=None,
        action_recommendation=None,
        should_continue=True,
    )
    state.update(overrides)
    return state


# =========================================================================
# signal_detector
# =========================================================================


class TestSignalDetector:
    @patch("src.agent.nodes.signal_detector.settings")
    @patch("src.agent.nodes.signal_detector._get_tools")
    async def test_empty_signals_when_no_data(self, mock_get_tools, mock_settings, sample_account, sample_campaign, sample_contact):
        mock_settings.USE_APOLLO_ENRICHMENT = False
        mock_news = AsyncMock()
        mock_news.run = AsyncMock(side_effect=Exception("No news"))
        mock_web = AsyncMock()
        mock_web.run = AsyncMock(side_effect=Exception("No web"))
        mock_get_tools.return_value = (mock_news, mock_web)

        from src.agent.nodes.signal_detector import signal_detector

        state = _qual_state(sample_account, sample_campaign, sample_contact)
        result = await signal_detector(state)
        assert result["signals"] == []

    @patch("src.agent.nodes.signal_detector.call_claude")
    @patch("src.agent.nodes.signal_detector.settings")
    @patch("src.agent.nodes.signal_detector._get_tools")
    async def test_detects_signals(self, mock_get_tools, mock_settings, mock_call_claude, sample_account, sample_campaign, sample_contact):
        mock_settings.USE_APOLLO_ENRICHMENT = False
        mock_settings.CLAUDE_HAIKU_MODEL = "claude-haiku-4-5-20251001"

        mock_news = AsyncMock()
        mock_news.run = AsyncMock(return_value=[
            {"title": "Acme raises Series B", "summary": "Raised $50M"},
        ])
        mock_web = AsyncMock()
        mock_web.run = AsyncMock(return_value={"content": "Pricing page content"})
        mock_get_tools.return_value = (mock_news, mock_web)

        mock_call_claude.return_value = json.dumps([
            {
                "signal_type": "funding",
                "observed_fact": "Raised Series B",
                "possible_implication": "Growth phase",
                "source": "news",
                "confidence": 0.85,
                "event_date": "2026-01-15",
            }
        ])

        from src.agent.nodes.signal_detector import signal_detector

        state = _qual_state(sample_account, sample_campaign, sample_contact)
        result = await signal_detector(state)
        assert len(result["signals"]) == 1
        assert result["signals"][0].signal_type == SignalType.FUNDING
        assert result["signals"][0].observed_fact == "Raised Series B"

    @patch("src.agent.nodes.signal_detector.call_claude")
    @patch("src.agent.nodes.signal_detector.settings")
    @patch("src.agent.nodes.signal_detector._get_tools")
    async def test_handles_invalid_json(self, mock_get_tools, mock_settings, mock_call_claude, sample_account, sample_campaign, sample_contact):
        mock_settings.USE_APOLLO_ENRICHMENT = False
        mock_settings.CLAUDE_HAIKU_MODEL = "claude-haiku-4-5-20251001"

        mock_news = AsyncMock()
        mock_news.run = AsyncMock(return_value=[{"title": "News", "summary": "Something"}])
        mock_web = AsyncMock()
        mock_web.run = AsyncMock(side_effect=Exception("fail"))
        mock_get_tools.return_value = (mock_news, mock_web)

        mock_call_claude.return_value = "not valid json {{"

        from src.agent.nodes.signal_detector import signal_detector

        state = _qual_state(sample_account, sample_campaign, sample_contact)
        result = await signal_detector(state)
        assert result["signals"] == []

    @patch("src.agent.nodes.signal_detector.call_claude")
    @patch("src.agent.nodes.signal_detector.settings")
    @patch("src.agent.nodes.signal_detector._get_tools")
    async def test_filters_unknown_signal_types(self, mock_get_tools, mock_settings, mock_call_claude, sample_account, sample_campaign, sample_contact):
        mock_settings.USE_APOLLO_ENRICHMENT = False
        mock_settings.CLAUDE_HAIKU_MODEL = "claude-haiku-4-5-20251001"

        mock_news = AsyncMock()
        mock_news.run = AsyncMock(return_value=[{"title": "News", "summary": "X"}])
        mock_web = AsyncMock()
        mock_web.run = AsyncMock(side_effect=Exception("fail"))
        mock_get_tools.return_value = (mock_news, mock_web)

        mock_call_claude.return_value = json.dumps([
            {"signal_type": "totally_fake_type", "observed_fact": "X", "possible_implication": "Y"},
            {"signal_type": "funding", "observed_fact": "Raised $10M", "possible_implication": "Growth"},
        ])

        from src.agent.nodes.signal_detector import signal_detector

        state = _qual_state(sample_account, sample_campaign, sample_contact)
        result = await signal_detector(state)
        assert len(result["signals"]) == 1
        assert result["signals"][0].signal_type == SignalType.FUNDING

    @patch("src.agent.nodes.signal_detector.call_claude")
    @patch("src.agent.nodes.signal_detector.settings")
    @patch("src.agent.nodes.signal_detector._get_tools")
    async def test_returns_error_on_exception(self, mock_get_tools, mock_settings, mock_call_claude, sample_account, sample_campaign, sample_contact):
        mock_settings.USE_APOLLO_ENRICHMENT = False
        mock_settings.CLAUDE_HAIKU_MODEL = "claude-haiku-4-5-20251001"

        mock_news = AsyncMock()
        mock_news.run = AsyncMock(return_value=[{"title": "X", "summary": "Y"}])
        mock_web = AsyncMock()
        mock_web.run = AsyncMock(side_effect=Exception("fail"))
        mock_get_tools.return_value = (mock_news, mock_web)

        mock_call_claude.side_effect = RuntimeError("LLM down")

        from src.agent.nodes.signal_detector import signal_detector

        state = _qual_state(sample_account, sample_campaign, sample_contact)
        result = await signal_detector(state)
        assert result["signals"] == []
        assert "error" in result


# =========================================================================
# crm_writer
# =========================================================================


class TestCrmWriter:
    async def test_returns_empty_when_no_account(self, sample_campaign):
        from src.agent.nodes.crm_writer import crm_writer

        state = QualificationState(
            thread_id="t-001",
            workspace_id="ws-001",
            campaign=sample_campaign,
            current_account=None,
        )
        result = await crm_writer(state)
        assert result == {}

    @patch("src.agent.nodes.crm_writer.async_session_factory")
    @patch("src.agent.nodes.crm_writer.save_seller_brief", new_callable=AsyncMock)
    @patch("src.agent.nodes.crm_writer.save_account_score", new_callable=AsyncMock)
    @patch("src.agent.nodes.crm_writer._get_hubspot")
    async def test_writes_score_to_hubspot(
        self,
        mock_get_hubspot,
        mock_save_score,
        mock_save_brief,
        mock_session_factory,
        sample_account,
        sample_campaign,
        sample_contact,
        sample_score,
    ):
        mock_hubspot = AsyncMock()
        mock_get_hubspot.return_value = mock_hubspot

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.begin = MagicMock(return_value=mock_session)
        mock_session_factory.return_value = mock_session

        from src.agent.nodes.crm_writer import crm_writer

        state = _qual_state(
            sample_account,
            sample_campaign,
            sample_contact,
            account_score=sample_score,
        )
        result = await crm_writer(state)
        assert result == {}
        mock_hubspot.run.assert_called()

    @patch("src.agent.nodes.crm_writer.async_session_factory")
    @patch("src.agent.nodes.crm_writer.save_seller_brief", new_callable=AsyncMock)
    @patch("src.agent.nodes.crm_writer.save_account_score", new_callable=AsyncMock)
    @patch("src.agent.nodes.crm_writer._get_hubspot")
    async def test_handles_hubspot_error(
        self,
        mock_get_hubspot,
        mock_save_score,
        mock_save_brief,
        mock_session_factory,
        sample_account,
        sample_campaign,
        sample_contact,
        sample_score,
    ):
        mock_hubspot = AsyncMock()
        mock_hubspot.run = AsyncMock(side_effect=Exception("HubSpot API error"))
        mock_get_hubspot.return_value = mock_hubspot

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.begin = MagicMock(return_value=mock_session)
        mock_session_factory.return_value = mock_session

        from src.agent.nodes.crm_writer import crm_writer

        state = _qual_state(
            sample_account,
            sample_campaign,
            sample_contact,
            account_score=sample_score,
        )
        # Should not raise — errors are logged and execution continues
        result = await crm_writer(state)
        assert result == {}

    @patch("src.agent.nodes.crm_writer.async_session_factory")
    @patch("src.agent.nodes.crm_writer.save_seller_brief", new_callable=AsyncMock)
    @patch("src.agent.nodes.crm_writer.save_account_score", new_callable=AsyncMock)
    @patch("src.agent.nodes.crm_writer._get_hubspot")
    async def test_persists_brief_to_postgres(
        self,
        mock_get_hubspot,
        mock_save_score,
        mock_save_brief,
        mock_session_factory,
        sample_account,
        sample_campaign,
        sample_contact,
        sample_score,
        sample_brief,
    ):
        mock_hubspot = AsyncMock()
        mock_get_hubspot.return_value = mock_hubspot

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.begin = MagicMock(return_value=mock_session)
        mock_session_factory.return_value = mock_session

        from src.agent.nodes.crm_writer import crm_writer

        state = _qual_state(
            sample_account,
            sample_campaign,
            sample_contact,
            account_score=sample_score,
            seller_brief=sample_brief,
        )
        await crm_writer(state)
        mock_save_score.assert_awaited_once()
        mock_save_brief.assert_awaited_once()

    @patch("src.agent.nodes.crm_writer.async_session_factory")
    @patch("src.agent.nodes.crm_writer._get_hubspot")
    async def test_handles_postgres_error(
        self,
        mock_get_hubspot,
        mock_session_factory,
        sample_account,
        sample_campaign,
        sample_contact,
        sample_score,
    ):
        mock_hubspot = AsyncMock()
        mock_get_hubspot.return_value = mock_hubspot

        mock_session_factory.side_effect = Exception("DB connection failed")

        from src.agent.nodes.crm_writer import crm_writer

        state = _qual_state(
            sample_account,
            sample_campaign,
            sample_contact,
            account_score=sample_score,
        )
        # Should not raise — errors are logged
        result = await crm_writer(state)
        assert result == {}
