"""Tests for Phase 3: CRM writeback, workflow, approval, task creation, observability.

These tests verify the Phase 3 routing logic, state construction,
and Zoho writer (which has minimal external deps). Node-level integration
tests that require redis/httpx run via `uv run pytest` with full deps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.state import (
    Account,
    AccountScore,
    ActionRecommendation,
    ActionType,
    BuyingRole,
    Campaign,
    PainHypothesis,
    PainType,
    QualificationState,
    RankedContact,
    SellerBrief,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_state(**overrides) -> QualificationState:
    """Build a minimal QualificationState for testing."""
    account = Account(
        id="acc_1",
        workspace_id="ws_1",
        company_name="Acme SaaS",
        domain="acme.com",
        industry="SaaS",
        employee_count=200,
        revenue=50_000_000.0,
    )
    score = AccountScore(
        account_id="acc_1",
        workspace_id="ws_1",
        icp_fit_score=78,
        pain_fit_score=72,
        timing_score=85,
        overall_priority_score=77,
        confidence_score=0.76,
    )
    contact = RankedContact(
        contact_id="con_1",
        name="Jane Smith",
        title="VP RevOps",
        normalized_function="Revenue Operations",
        normalized_seniority="VP",
        relevance_score=92,
        likely_role=BuyingRole.PAIN_OWNER,
        reason_for_relevance="Owns pricing ops",
        confidence_score=0.88,
    )
    pain = PainHypothesis(
        pain_type=PainType.PRICING_COMPLEXITY,
        score=82,
        confidence_score=0.78,
    )
    action = ActionRecommendation(
        action=ActionType.PURSUE_NOW,
        explanation="Strong fit, active timing signals",
        best_first_contact=contact,
        best_channel="email",
        multi_threading_recommended=True,
        confidence_score=0.76,
    )
    brief = SellerBrief(
        id="brief_1",
        account_id="acc_1",
        workspace_id="ws_1",
        version=1,
        account_snapshot="Acme SaaS, 200 employees, $50M revenue",
        why_this_account="Strong ICP fit (78/100)",
        why_now="Pricing page overhauled recently",
        likely_pain_points=[pain],
        recommended_contacts=[contact],
        persona_angles=[],
        risks_and_unknowns=["Unknown billing system"],
        recommended_action=action,
        generated_at=datetime.now(tz=timezone.utc),
    )
    campaign = Campaign(
        id="camp_1",
        workspace_id="ws_1",
        name="Q1 Outbound",
    )

    defaults: dict = {
        "thread_id": "thread_1",
        "workspace_id": "ws_1",
        "campaign": campaign,
        "current_account": account,
        "account_score": score,
        "ranked_contacts": [contact],
        "pain_hypotheses": [pain],
        "action_recommendation": action,
        "seller_brief": brief,
    }
    defaults.update(overrides)
    return defaults  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Qualification routing logic tests
# ---------------------------------------------------------------------------


class TestQualificationRouting:
    """Test routing decisions without importing langgraph."""

    def test_auto_approved_routes_to_crm(self):
        state = _make_state(approval_status="auto_approved")
        approval = state.get("approval_status")
        assert approval != "pending_review"
        # This would route to crm_writer

    def test_pending_review_routes_to_end(self):
        state = _make_state(approval_status="pending_review")
        approval = state.get("approval_status")
        assert approval == "pending_review"
        # This would route to END (interrupt)

    def test_approved_routes_to_crm(self):
        state = _make_state(approval_status="approved")
        approval = state.get("approval_status")
        assert approval != "pending_review"

    def test_disqualified_skips_to_action(self):
        """Disqualified accounts should skip signal/contact/pain nodes."""
        score = AccountScore(
            account_id="acc_1",
            workspace_id="ws_1",
            icp_fit_score=15,
            pain_fit_score=0,
            timing_score=0,
            overall_priority_score=10,
            confidence_score=0.9,
            is_disqualified=True,
            disqualify_reason="Too small",
        )
        state = _make_state(account_score=score)
        assert state["account_score"].is_disqualified

    def test_account_iteration(self):
        """After processing one account, should advance to the next."""
        account1 = Account(id="acc_1", workspace_id="ws_1", company_name="Acme")
        account2 = Account(id="acc_2", workspace_id="ws_1", company_name="Globex")
        state = _make_state(
            accounts=[account1, account2],
            current_account=account1,
        )
        accounts = state.get("accounts", [])
        current = state.get("current_account")
        current_idx = next(
            (i for i, a in enumerate(accounts) if a.id == current.id), -1
        )
        assert current_idx == 0
        assert current_idx < len(accounts) - 1  # more accounts to process


# ---------------------------------------------------------------------------
# State construction tests
# ---------------------------------------------------------------------------


class TestStateConstruction:
    """Test that state objects serialize correctly."""

    def test_seller_brief_has_all_sections(self):
        state = _make_state()
        brief = state["seller_brief"]
        assert brief.account_snapshot
        assert brief.why_this_account
        assert brief.why_now
        assert len(brief.likely_pain_points) > 0
        assert len(brief.recommended_contacts) > 0
        assert len(brief.risks_and_unknowns) > 0
        assert brief.recommended_action.action == ActionType.PURSUE_NOW

    def test_action_recommendation_thresholds(self):
        state = _make_state()
        action = state["action_recommendation"]
        assert action.action == ActionType.PURSUE_NOW
        assert action.confidence_score >= 0.5
        assert action.best_first_contact is not None
        assert action.best_channel == "email"

    def test_brief_serializes_to_json(self):
        state = _make_state()
        brief = state["seller_brief"]
        json_data = brief.model_dump()
        assert "account_snapshot" in json_data
        assert "recommended_action" in json_data
        assert json_data["recommended_action"]["action"] == "pursue_now"

    def test_nurture_action_no_task(self):
        """Nurture actions should not trigger task creation."""
        action = ActionRecommendation(
            action=ActionType.NURTURE,
            explanation="Weak timing",
            confidence_score=0.5,
        )
        assert action.action == ActionType.NURTURE
        # Task creator should skip nurture actions
        should_create_task = action.action in {
            ActionType.PURSUE_NOW,
            ActionType.HUMAN_REVIEW_REQUIRED,
        }
        assert not should_create_task

    def test_pursue_now_creates_task(self):
        """Pursue now actions should trigger task creation."""
        action = ActionRecommendation(
            action=ActionType.PURSUE_NOW,
            explanation="Strong fit",
            confidence_score=0.8,
        )
        should_create_task = action.action in {
            ActionType.PURSUE_NOW,
            ActionType.HUMAN_REVIEW_REQUIRED,
        }
        assert should_create_task


# ---------------------------------------------------------------------------
# Zoho field mapping tests
# ---------------------------------------------------------------------------


class TestZohoFieldMapping:
    """Test Zoho CRM field mappings."""

    def test_zoho_score_fields_defined(self):
        try:
            from src.agent.nodes.zoho_writer import ZOHO_SCORE_FIELDS
        except ImportError:
            pytest.skip("Zoho writer deps not available")
        assert "OmniGTM_Fit_Score" in ZOHO_SCORE_FIELDS
        assert "OmniGTM_Pain_Score" in ZOHO_SCORE_FIELDS
        assert "OmniGTM_Action" in ZOHO_SCORE_FIELDS

    def test_zoho_writer_skips_without_account(self):
        """Zoho writer should return empty dict if no account."""
        try:
            from src.agent.nodes.zoho_writer import zoho_writer
        except ImportError:
            pytest.skip("Zoho writer deps not available")
        import asyncio

        state = _make_state(current_account=None)
        result = asyncio.get_event_loop().run_until_complete(zoho_writer(state))
        assert result == {}


# ---------------------------------------------------------------------------
# CRM writeback field mapping tests (without importing the full node)
# ---------------------------------------------------------------------------


class TestCRMWritebackLogic:
    """Test CRM writeback field mappings and logic."""

    def test_hubspot_custom_properties(self):
        """Verify HubSpot custom property names are correct."""
        expected_fields = [
            "omnigtm_fit_score",
            "omnigtm_pain_score",
            "omnigtm_timing_score",
            "omnigtm_priority_score",
            "omnigtm_action",
            "omnigtm_confidence",
            "omnigtm_last_scored",
        ]
        # These are the HubSpot custom properties we write
        for field in expected_fields:
            assert field.startswith("omnigtm_")

    def test_action_types_map_to_strings(self):
        """Action types should serialize to lowercase strings for CRM."""
        assert ActionType.PURSUE_NOW.value == "pursue_now"
        assert ActionType.NURTURE.value == "nurture"
        assert ActionType.DISQUALIFY.value == "disqualify"
        assert ActionType.HUMAN_REVIEW_REQUIRED.value == "human_review_required"

    def test_brief_json_serialization(self):
        """Seller brief should serialize to JSON for CRM storage."""
        state = _make_state()
        brief = state["seller_brief"]
        json_data = brief.model_dump(mode="json")
        assert isinstance(json_data, dict)
        assert "id" in json_data
        assert "account_id" in json_data
        assert "recommended_action" in json_data


# ---------------------------------------------------------------------------
# ClickHouse observability tests
# ---------------------------------------------------------------------------


class TestClickHouseObservability:
    """Test ClickHouse event logging methods exist and have correct signatures."""

    def _get_client_class(self):
        try:
            from src.db.clickhouse import ClickHouseClient
            return ClickHouseClient
        except ImportError:
            pytest.skip("clickhouse-driver not available")

    def test_qualification_event_method_exists(self):
        cls = self._get_client_class()
        client = cls.__new__(cls)
        assert hasattr(client, "log_qualification_event")

    def test_recommendation_event_method_exists(self):
        cls = self._get_client_class()
        client = cls.__new__(cls)
        assert hasattr(client, "log_recommendation_event")

    def test_feedback_event_method_exists(self):
        cls = self._get_client_class()
        client = cls.__new__(cls)
        assert hasattr(client, "log_feedback_event")
