"""Tests for qualification pipeline nodes: action_recommender, brief_builder, auto_outbound_gate."""

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
from src.guardrails.send_caps import SendCapError

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_ACCOUNT = Account(
    id="acct-001",
    workspace_id="ws-test-001",
    company_name="Acme Corp",
    domain="acme.com",
    industry="SaaS",
    employee_count=250,
    revenue=15_000_000.0,
)

SAMPLE_SCORE = AccountScore(
    account_id="acct-001",
    workspace_id="ws-test-001",
    icp_fit_score=85,
    pain_fit_score=80,
    timing_score=90,
    overall_priority_score=88,
    confidence_score=0.9,
    fit_reasons=[
        Evidence(
            statement="Strong ICP fit",
            evidence_type=EvidenceType.FACT,
            source="enrichment",
        )
    ],
)

SAMPLE_CONTACT = RankedContact(
    contact_id="contact-001",
    name="Jane Doe",
    title="VP Revenue Operations",
    normalized_function="revops",
    normalized_seniority="vp",
    relevance_score=90,
    likely_role=BuyingRole.PAIN_OWNER,
    reason_for_relevance="Owns pricing stack",
    confidence_score=0.85,
)

SAMPLE_PAIN = PainHypothesis(
    pain_type=PainType.PRICING_COMPLEXITY,
    score=85,
    supporting_facts=[
        Evidence(
            statement="Multiple pricing tiers observed",
            evidence_type=EvidenceType.FACT,
            source="website",
        )
    ],
    unknowns=["Current billing provider"],
    confidence_score=0.8,
)

SAMPLE_SIGNAL_1 = Signal(
    id="sig-001",
    account_id="acct-001",
    workspace_id="ws-test-001",
    signal_type=SignalType.PRICING_CHANGE,
    source="news",
    observed_fact="Announced pricing overhaul",
    possible_implication="May need pricing infrastructure",
    event_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
    confidence=0.9,
)

SAMPLE_SIGNAL_2 = Signal(
    id="sig-002",
    account_id="acct-001",
    workspace_id="ws-test-001",
    signal_type=SignalType.HIRING_REVOPS_PRICING,
    source="linkedin",
    observed_fact="Hiring RevOps manager",
    possible_implication="Building out pricing team",
    event_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
    confidence=0.85,
)

SAMPLE_VALUE_PROP = ValuePropRecommendation(
    contact_id="contact-001",
    top_problem="Pricing complexity slowing deal velocity",
    relevant_capability="Automated pricing engine",
    expected_business_outcome="30% faster quote-to-cash",
    one_line_hook="Stop losing deals to pricing confusion",
    short_value_prop="Our platform automates complex pricing so your team closes faster.",
    likely_objection="Already using Salesforce CPQ",
    suggested_response="We complement CPQ with real-time pricing intelligence.",
    confidence_score=0.85,
)

SAMPLE_RECOMMENDATION = ActionRecommendation(
    action=ActionType.PURSUE_NOW,
    explanation="High ICP fit with strong timing signals",
    best_first_contact=SAMPLE_CONTACT,
    confidence_score=0.9,
)

SAMPLE_BRIEF = SellerBrief(
    id="brief-001",
    account_id="acct-001",
    workspace_id="ws-test-001",
    account_snapshot="Acme Corp is a mid-market SaaS company.",
    why_this_account="Strong ICP fit, active pricing overhaul.",
    why_now="Recent pricing change announcement.",
    likely_pain_points=[SAMPLE_PAIN],
    recommended_contacts=[SAMPLE_CONTACT],
    persona_angles=[SAMPLE_VALUE_PROP],
    risks_and_unknowns=["Unknown billing provider"],
    recommended_action=SAMPLE_RECOMMENDATION,
    signals_used=[SAMPLE_SIGNAL_1, SAMPLE_SIGNAL_2],
    sources_consulted=["news", "linkedin"],
    scoring=SAMPLE_SCORE,
    generated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
)

SAMPLE_CAMPAIGN = Campaign(
    id="camp-001",
    workspace_id="ws-test-001",
    name="Q1 Outbound",
    sequence_config={"automation": {"enabled": True}},
)


def _base_state(**overrides: object) -> QualificationState:
    """Build a minimal QualificationState dict with overrides."""
    base: QualificationState = {
        "thread_id": "thread-test-001",
        "workspace_id": "ws-test-001",
        "current_account": SAMPLE_ACCOUNT,
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


# =========================================================================
# action_recommender
# =========================================================================


class TestActionRecommender:
    """Tests for src.agent.nodes.action_recommender."""

    async def test_returns_human_review_when_no_score(self):
        """When account_score is None, return HUMAN_REVIEW_REQUIRED."""
        from src.agent.nodes.action_recommender import action_recommender

        state = _base_state(account_score=None)
        result = await action_recommender(state)

        assert "action_recommendation" in result
        rec = result["action_recommendation"]
        assert isinstance(rec, ActionRecommendation)
        assert rec.action == ActionType.HUMAN_REVIEW_REQUIRED
        assert rec.confidence_score == 0.0
        assert "No account score" in rec.explanation

    async def test_returns_error_when_no_account(self):
        """When current_account is missing, return error."""
        from src.agent.nodes.action_recommender import action_recommender

        state = _base_state(current_account=None)
        result = await action_recommender(state)

        assert result == {"error": "No current_account set"}

    @patch("src.agent.nodes.action_recommender.recommend_action")
    async def test_calls_recommend_action_with_correct_args(self, mock_recommend):
        """When score exists, delegate to recommend_action with score, top_contact, pain_hypotheses."""
        from src.agent.nodes.action_recommender import action_recommender

        mock_recommend.return_value = SAMPLE_RECOMMENDATION

        state = _base_state(
            account_score=SAMPLE_SCORE,
            ranked_contacts=[SAMPLE_CONTACT],
            pain_hypotheses=[SAMPLE_PAIN],
        )
        result = await action_recommender(state)

        mock_recommend.assert_called_once_with(
            score=SAMPLE_SCORE,
            top_contact=SAMPLE_CONTACT,
            pain_hypotheses=[SAMPLE_PAIN],
        )
        assert result["action_recommendation"] is SAMPLE_RECOMMENDATION

    @patch("src.agent.nodes.action_recommender.recommend_action")
    async def test_top_contact_is_none_when_no_contacts(self, mock_recommend):
        """When ranked_contacts is empty, top_contact should be None."""
        from src.agent.nodes.action_recommender import action_recommender

        mock_recommend.return_value = SAMPLE_RECOMMENDATION

        state = _base_state(
            account_score=SAMPLE_SCORE,
            ranked_contacts=[],
            pain_hypotheses=[],
        )
        await action_recommender(state)

        mock_recommend.assert_called_once_with(
            score=SAMPLE_SCORE,
            top_contact=None,
            pain_hypotheses=[],
        )

    @patch("src.agent.nodes.action_recommender.recommend_action")
    async def test_result_dict_contains_action_recommendation_key(self, mock_recommend):
        """Result dict should have exactly `action_recommendation` key."""
        from src.agent.nodes.action_recommender import action_recommender

        mock_recommend.return_value = SAMPLE_RECOMMENDATION

        state = _base_state(account_score=SAMPLE_SCORE)
        result = await action_recommender(state)

        assert set(result.keys()) == {"action_recommendation"}


# =========================================================================
# brief_builder
# =========================================================================


class TestBriefBuilder:
    """Tests for src.agent.nodes.brief_builder."""

    async def test_returns_error_when_no_account(self):
        """When current_account is missing, return error."""
        from src.agent.nodes.brief_builder import brief_builder

        state = _base_state(current_account=None)
        result = await brief_builder(state)

        assert result == {"error": "No current_account set"}

    @patch("src.agent.nodes.brief_builder.settings")
    @patch("src.agent.nodes.brief_builder.call_claude", new_callable=AsyncMock)
    async def test_calls_claude_with_brief_generation_task(self, mock_claude, mock_settings):
        """call_claude should be called with task='brief_generation'."""
        from src.agent.nodes.brief_builder import brief_builder

        mock_settings.CLAUDE_MODEL = "claude-sonnet-4-6"
        mock_claude.return_value = json.dumps({
            "account_snapshot": "Acme Corp snapshot",
            "why_this_account": "Strong fit",
            "why_now": "Pricing change",
            "risks_and_unknowns": ["Unknown billing provider"],
        })

        state = _base_state(
            account_score=SAMPLE_SCORE,
            ranked_contacts=[SAMPLE_CONTACT],
            pain_hypotheses=[SAMPLE_PAIN],
            signals=[SAMPLE_SIGNAL_1],
            value_props=[SAMPLE_VALUE_PROP],
            action_recommendation=SAMPLE_RECOMMENDATION,
        )
        await brief_builder(state)

        mock_claude.assert_called_once()
        call_kwargs = mock_claude.call_args
        assert call_kwargs.kwargs["task"] == "brief_generation"
        assert call_kwargs.kwargs["workspace_id"] == "ws-test-001"
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4-6"

    @patch("src.agent.nodes.brief_builder.settings")
    @patch("src.agent.nodes.brief_builder.call_claude", new_callable=AsyncMock)
    async def test_parses_valid_json_into_seller_brief(self, mock_claude, mock_settings):
        """Valid JSON response should be parsed into a SellerBrief."""
        from src.agent.nodes.brief_builder import brief_builder

        mock_settings.CLAUDE_MODEL = "claude-sonnet-4-6"
        mock_claude.return_value = json.dumps({
            "account_snapshot": "Acme Corp is a mid-market SaaS.",
            "why_this_account": "Strong ICP fit.",
            "why_now": "Active pricing overhaul.",
            "risks_and_unknowns": ["Unknown billing provider"],
        })

        state = _base_state(
            account_score=SAMPLE_SCORE,
            ranked_contacts=[SAMPLE_CONTACT],
            pain_hypotheses=[SAMPLE_PAIN],
            signals=[SAMPLE_SIGNAL_1],
            value_props=[SAMPLE_VALUE_PROP],
            action_recommendation=SAMPLE_RECOMMENDATION,
        )
        result = await brief_builder(state)

        assert "seller_brief" in result
        brief = result["seller_brief"]
        assert isinstance(brief, SellerBrief)
        assert brief.account_snapshot == "Acme Corp is a mid-market SaaS."
        assert brief.why_this_account == "Strong ICP fit."
        assert brief.why_now == "Active pricing overhaul."
        assert brief.risks_and_unknowns == ["Unknown billing provider"]
        assert brief.account_id == "acct-001"
        assert brief.workspace_id == "ws-test-001"
        assert brief.recommended_contacts == [SAMPLE_CONTACT]
        assert brief.likely_pain_points == [SAMPLE_PAIN]

    @patch("src.agent.nodes.brief_builder.settings")
    @patch("src.agent.nodes.brief_builder.call_claude", new_callable=AsyncMock)
    async def test_handles_json_parse_failure_gracefully(self, mock_claude, mock_settings):
        """When JSON parsing fails, still return a SellerBrief with empty fields."""
        from src.agent.nodes.brief_builder import brief_builder

        mock_settings.CLAUDE_MODEL = "claude-sonnet-4-6"
        mock_claude.return_value = "This is not valid JSON at all {{{broken"

        state = _base_state(
            account_score=SAMPLE_SCORE,
            ranked_contacts=[SAMPLE_CONTACT],
            pain_hypotheses=[SAMPLE_PAIN],
            signals=[],
            value_props=[],
            action_recommendation=SAMPLE_RECOMMENDATION,
        )
        result = await brief_builder(state)

        assert "seller_brief" in result
        brief = result["seller_brief"]
        assert isinstance(brief, SellerBrief)
        # Fields should be empty strings when JSON parse fails
        assert brief.account_snapshot == ""
        assert brief.why_this_account == ""
        assert brief.why_now == ""
        assert brief.risks_and_unknowns == []

    @patch("src.agent.nodes.brief_builder.settings")
    @patch("src.agent.nodes.brief_builder.call_claude", new_callable=AsyncMock)
    async def test_catches_exception_and_returns_error(self, mock_claude, mock_settings):
        """When call_claude raises, return error and seller_brief=None."""
        from src.agent.nodes.brief_builder import brief_builder

        mock_settings.CLAUDE_MODEL = "claude-sonnet-4-6"
        mock_claude.side_effect = RuntimeError("LLM service unavailable")

        state = _base_state(account_score=SAMPLE_SCORE)
        result = await brief_builder(state)

        assert "error" in result
        assert "LLM service unavailable" in result["error"]
        assert result["seller_brief"] is None

    @patch("src.agent.nodes.brief_builder.settings")
    @patch("src.agent.nodes.brief_builder.call_claude", new_callable=AsyncMock)
    async def test_sources_consulted_includes_signals_and_enrichment(
        self, mock_claude, mock_settings
    ):
        """sources_consulted should contain unique signal sources and 'enrichment_research'."""
        from src.agent.nodes.brief_builder import brief_builder

        mock_settings.CLAUDE_MODEL = "claude-sonnet-4-6"
        mock_claude.return_value = json.dumps({
            "account_snapshot": "snapshot",
            "why_this_account": "fit",
            "why_now": "now",
            "risks_and_unknowns": [],
        })

        enrichment = MagicMock()
        state = _base_state(
            account_score=SAMPLE_SCORE,
            ranked_contacts=[],
            pain_hypotheses=[],
            signals=[SAMPLE_SIGNAL_1, SAMPLE_SIGNAL_2],
            value_props=[],
            enrichment=enrichment,
        )
        result = await brief_builder(state)

        brief = result["seller_brief"]
        assert "news" in brief.sources_consulted
        assert "linkedin" in brief.sources_consulted
        assert "enrichment_research" in brief.sources_consulted


# =========================================================================
# auto_outbound_gate
# =========================================================================


def _passing_state(**overrides: object) -> QualificationState:
    """Build a state that passes ALL auto-outbound checks by default."""
    base: QualificationState = {
        "thread_id": "thread-test-001",
        "workspace_id": "ws-test-001",
        "current_account": SAMPLE_ACCOUNT,
        "campaign": SAMPLE_CAMPAIGN,
        "account_score": SAMPLE_SCORE,
        "ranked_contacts": [SAMPLE_CONTACT],
        "pain_hypotheses": [SAMPLE_PAIN],
        "signals": [SAMPLE_SIGNAL_1, SAMPLE_SIGNAL_2],
        "action_recommendation": SAMPLE_RECOMMENDATION,
        "seller_brief": SAMPLE_BRIEF,
        "contacts": [],
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


class TestAutoOutboundGate:
    """Tests for src.agent.nodes.auto_outbound_gate."""

    @pytest.fixture(autouse=True)
    def _setup_guardrails(self):
        """Initialize guardrails with mock Redis and ClickHouse before each test."""
        import src.agent.nodes.auto_outbound_gate as gate_mod

        self.mock_redis = AsyncMock()
        self.mock_clickhouse = AsyncMock()
        gate_mod.init_guardrails(self.mock_redis, self.mock_clickhouse)

        # Store references to the module-level guardrail instances
        self.gate_mod = gate_mod
        self.mock_kill_switch = AsyncMock()
        self.mock_blocklist = AsyncMock()
        self.mock_send_caps = AsyncMock()

        # Default: all guardrails pass
        self.mock_kill_switch.is_paused = AsyncMock(return_value=(False, ""))
        self.mock_blocklist.is_blocked = AsyncMock(return_value=(False, ""))
        self.mock_send_caps.check_and_increment = AsyncMock()

        yield

        # Reset module-level state
        gate_mod._redis = None
        gate_mod._kill_switch = None
        gate_mod._blocklist = None
        gate_mod._send_caps = None
        gate_mod._clickhouse = None

    def _patch_guardrails(self):
        """Return a context manager that patches all three guardrails."""
        return (
            patch.object(self.gate_mod, "_kill_switch", self.mock_kill_switch),
            patch.object(self.gate_mod, "_blocklist", self.mock_blocklist),
            patch.object(self.gate_mod, "_send_caps", self.mock_send_caps),
        )

    async def test_skips_when_automation_disabled(self):
        """When automation is disabled for the workspace, skip outbound."""
        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        disabled_campaign = Campaign(
            id="camp-001",
            workspace_id="ws-test-001",
            name="Q1 Outbound",
            sequence_config={"automation": {"enabled": False}},
        )
        state = _passing_state(campaign=disabled_campaign)

        p1, p2, p3 = self._patch_guardrails()
        with p1, p2, p3:
            result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is False
        assert "automation_disabled" in result["auto_outbound_skip_reason"]

    async def test_skips_when_kill_switch_active(self):
        """When kill switch is active, skip outbound."""
        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        self.mock_kill_switch.is_paused = AsyncMock(
            return_value=(True, "error_rate_exceeded")
        )
        state = _passing_state()

        p1, p2, p3 = self._patch_guardrails()
        with p1, p2, p3:
            result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is False
        assert "kill_switch_active" in result["auto_outbound_skip_reason"]

    async def test_skips_when_action_not_pursue_now(self):
        """When action is not pursue_now, skip outbound."""
        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        nurture_rec = ActionRecommendation(
            action=ActionType.NURTURE,
            explanation="Not ready yet",
            confidence_score=0.7,
        )
        state = _passing_state(action_recommendation=nurture_rec)

        p1, p2, p3 = self._patch_guardrails()
        with p1, p2, p3:
            result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is False
        assert "action_not_pursue_now" in result["auto_outbound_skip_reason"]

    async def test_skips_when_thresholds_not_met(self):
        """When overall_priority_score is below threshold, skip outbound."""
        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        low_score = AccountScore(
            account_id="acct-001",
            workspace_id="ws-test-001",
            icp_fit_score=50,
            pain_fit_score=40,
            timing_score=45,
            overall_priority_score=45,  # below 80 threshold
            confidence_score=0.9,
        )
        state = _passing_state(account_score=low_score)

        p1, p2, p3 = self._patch_guardrails()
        with p1, p2, p3:
            result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is False
        assert "threshold_not_met" in result["auto_outbound_skip_reason"]

    async def test_skips_when_blocklisted(self):
        """When account domain is blocklisted, skip outbound."""
        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        self.mock_blocklist.is_blocked = AsyncMock(
            return_value=(True, "domain_blocklisted")
        )
        state = _passing_state()

        p1, p2, p3 = self._patch_guardrails()
        with p1, p2, p3:
            result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is False
        assert "blocklisted" in result["auto_outbound_skip_reason"]

    async def test_skips_when_send_cap_exceeded(self):
        """When send cap is exceeded, skip outbound."""
        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        self.mock_send_caps.check_and_increment = AsyncMock(
            side_effect=SendCapError(
                cap_type="daily_max_per_workspace", current=25, limit=25
            )
        )
        state = _passing_state()

        p1, p2, p3 = self._patch_guardrails()
        with p1, p2, p3:
            result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is False
        assert "send_cap_exceeded" in result["auto_outbound_skip_reason"]

    @patch("src.agent.nodes.auto_outbound_gate.enqueue_by_event", new_callable=AsyncMock)
    async def test_triggers_outbound_when_all_checks_pass(self, mock_enqueue):
        """When all guardrail checks pass, trigger outbound and enqueue job."""
        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        state = _passing_state()

        p1, p2, p3 = self._patch_guardrails()
        with p1, p2, p3, \
             patch("src.agent.nodes.auto_outbound_gate.settings") as mock_settings:
            mock_settings.OUTBOUND_DRAFT_ONLY = False
            result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is True
        assert "auto_outbound_skip_reason" not in result

        mock_enqueue.assert_called_once()
        call_kwargs = mock_enqueue.call_args
        assert call_kwargs.kwargs["event_type"] == "brief_to_outbound"
        assert call_kwargs.kwargs["workspace_id"] == "ws-test-001"
        payload = call_kwargs.kwargs["payload"]
        assert payload["brief_id"] == "brief-001"
        assert payload["account_id"] == "acct-001"
        assert payload["auto_triggered"] is True

    @patch("src.agent.nodes.auto_outbound_gate.enqueue_by_event", new_callable=AsyncMock)
    async def test_skips_when_no_action_recommendation(self, mock_enqueue):
        """When action_recommendation is None, skip (action_not_pursue_now)."""
        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        state = _passing_state(action_recommendation=None)

        p1, p2, p3 = self._patch_guardrails()
        with p1, p2, p3:
            result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is False
        assert "action_not_pursue_now" in result["auto_outbound_skip_reason"]
        mock_enqueue.assert_not_called()

    async def test_skips_when_confidence_below_threshold(self):
        """When account_score confidence is below threshold, skip outbound."""
        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        low_confidence_score = AccountScore(
            account_id="acct-001",
            workspace_id="ws-test-001",
            icp_fit_score=85,
            pain_fit_score=80,
            timing_score=90,
            overall_priority_score=88,
            confidence_score=0.5,  # below 0.80 threshold
        )
        state = _passing_state(account_score=low_confidence_score)

        p1, p2, p3 = self._patch_guardrails()
        with p1, p2, p3:
            result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is False
        assert "threshold_not_met" in result["auto_outbound_skip_reason"]

    async def test_skips_when_too_few_signals(self):
        """When fewer than min_signals, skip outbound."""
        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        state = _passing_state(signals=[SAMPLE_SIGNAL_1])  # only 1, need 2

        p1, p2, p3 = self._patch_guardrails()
        with p1, p2, p3:
            result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is False
        assert "threshold_not_met" in result["auto_outbound_skip_reason"]

    async def test_skips_when_too_many_unknowns(self):
        """When seller_brief has more than max_unknowns, skip outbound."""
        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        many_unknowns_brief = SellerBrief(
            id="brief-002",
            account_id="acct-001",
            workspace_id="ws-test-001",
            account_snapshot="snapshot",
            why_this_account="fit",
            why_now="now",
            likely_pain_points=[SAMPLE_PAIN],
            recommended_contacts=[SAMPLE_CONTACT],
            persona_angles=[SAMPLE_VALUE_PROP],
            risks_and_unknowns=["u1", "u2", "u3", "u4"],  # 4 > max 3
            recommended_action=SAMPLE_RECOMMENDATION,
        )
        state = _passing_state(seller_brief=many_unknowns_brief)

        p1, p2, p3 = self._patch_guardrails()
        with p1, p2, p3:
            result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is False
        assert "threshold_not_met" in result["auto_outbound_skip_reason"]
