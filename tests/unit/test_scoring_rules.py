"""Tests for OmniGTM deterministic scoring rules."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from src.agent.state import (
    Account,
    AccountScore,
    ActionType,
    BuyingRole,
    PainHypothesis,
    PainType,
    RankedContact,
    Signal,
    SignalType,
)
from src.scoring.icp_rules import score_icp_fit
from src.scoring.timing_rules import score_timing, _recency_score
from src.scoring.action_rules import recommend_action


# ---------------------------------------------------------------------------
# ICP Scoring
# ---------------------------------------------------------------------------


class TestICPScoring:
    def _make_account(self, **kwargs) -> Account:
        defaults = {
            "id": "acc_1",
            "workspace_id": "ws_1",
            "company_name": "Acme SaaS",
            "domain": "acme.com",
            "industry": "SaaS",
            "employee_count": 200,
            "revenue": 50_000_000.0,
            "metadata": {"geography": "US"},
        }
        defaults.update(kwargs)
        return Account(**defaults)

    def test_perfect_icp_match(self):
        account = self._make_account(
            metadata={"geography": "US", "signals": ["recent_funding", "product_launch"]},
        )
        score, fit, non_fit, is_dq, dq_reason, conf = score_icp_fit(account)
        assert score >= 60
        assert len(fit) > 0
        assert not is_dq
        assert conf > 0.5

    def test_wrong_industry(self):
        account = self._make_account(industry="Agriculture")
        score, fit, non_fit, is_dq, dq_reason, conf = score_icp_fit(account)
        assert score < 70
        assert any("not in ICP" in e.statement for e in non_fit)

    def test_too_small_company(self):
        account = self._make_account(employee_count=10)
        score, fit, non_fit, is_dq, dq_reason, conf = score_icp_fit(account)
        # 10 employees triggers disqualify rule if below 20
        assert is_dq
        assert score == 0

    def test_disqualify_existing_customer(self):
        account = self._make_account(metadata={"is_customer": True})
        score, fit, non_fit, is_dq, dq_reason, conf = score_icp_fit(account)
        assert is_dq
        assert score == 0

    def test_unknown_fields_neutral(self):
        account = self._make_account(
            industry=None,
            employee_count=None,
            revenue=None,
            metadata={},
        )
        score, fit, non_fit, is_dq, dq_reason, conf = score_icp_fit(account)
        # Unknown = neutral, should be around 50
        assert 40 <= score <= 60
        assert not is_dq

    def test_negative_signals_reduce_score(self):
        account = self._make_account(
            metadata={"geography": "US", "signals": ["hiring_freeze", "recent_layoffs"]},
        )
        score_neg, _, _, _, _, _ = score_icp_fit(account)

        account_pos = self._make_account(
            metadata={"geography": "US", "signals": ["recent_funding"]},
        )
        score_pos, _, _, _, _, _ = score_icp_fit(account_pos)

        assert score_neg < score_pos

    def test_custom_weights(self):
        account = self._make_account()
        custom_weights = {"industry": 0.80, "company_size": 0.20}
        score, _, _, _, _, _ = score_icp_fit(account, weights=custom_weights)
        # With 80% weight on industry (SaaS = match), score should be high
        assert score >= 70


# ---------------------------------------------------------------------------
# Timing Scoring
# ---------------------------------------------------------------------------


class TestTimingScoring:
    def _make_signal(self, days_ago: int = 0, reliability: float = 0.8) -> Signal:
        now = datetime.now(tz=timezone.utc)
        return Signal(
            id="sig_1",
            account_id="acc_1",
            workspace_id="ws_1",
            signal_type=SignalType.PRICING_CHANGE,
            source="web_scraper",
            observed_fact="Test signal",
            possible_implication="Test implication",
            event_date=now - timedelta(days=days_ago),
            reliability_score=reliability,
            confidence=0.8,
        )

    def test_no_signals_low_score(self):
        score, conf = score_timing([])
        assert score == 30
        assert conf < 0.3

    def test_fresh_signals_high_score(self):
        signals = [self._make_signal(days_ago=3)]
        score, conf = score_timing(signals)
        assert score >= 70

    def test_stale_signals_lower_score(self):
        fresh = [self._make_signal(days_ago=3)]
        stale = [self._make_signal(days_ago=90)]

        score_fresh, _ = score_timing(fresh)
        score_stale, _ = score_timing(stale)
        assert score_fresh > score_stale

    def test_expired_signals_ignored(self):
        signals = [self._make_signal(days_ago=200)]
        score, conf = score_timing(signals)
        assert score <= 30

    def test_multiple_signals_boost(self):
        one = [self._make_signal(days_ago=5)]
        many = [self._make_signal(days_ago=i) for i in range(1, 6)]

        score_one, _ = score_timing(one)
        score_many, _ = score_timing(many)
        assert score_many >= score_one

    def test_recency_score_fresh(self):
        now = datetime.now(tz=timezone.utc)
        assert _recency_score(now, now) == 1.0

    def test_recency_score_none(self):
        assert _recency_score(None) == 0.3


# ---------------------------------------------------------------------------
# Action Rules
# ---------------------------------------------------------------------------


class TestActionRules:
    def _make_score(self, **kwargs) -> AccountScore:
        defaults = {
            "account_id": "acc_1",
            "workspace_id": "ws_1",
            "icp_fit_score": 75,
            "pain_fit_score": 70,
            "timing_score": 80,
            "overall_priority_score": 75,
            "confidence_score": 0.75,
        }
        defaults.update(kwargs)
        return AccountScore(**defaults)

    def _make_contact(self, relevance: int = 85) -> RankedContact:
        return RankedContact(
            contact_id="con_1",
            name="Jane Smith",
            title="VP RevOps",
            normalized_function="Revenue Operations",
            normalized_seniority="VP",
            relevance_score=relevance,
            likely_role=BuyingRole.PAIN_OWNER,
            reason_for_relevance="Directly owns pricing",
            confidence_score=0.85,
        )

    def _make_pain(self, confidence: float = 0.7) -> PainHypothesis:
        return PainHypothesis(
            pain_type=PainType.PRICING_COMPLEXITY,
            score=80,
            confidence_score=confidence,
        )

    def test_pursue_now(self):
        result = recommend_action(
            self._make_score(overall_priority_score=75),
            self._make_contact(relevance=85),
            [self._make_pain(confidence=0.7)],
        )
        assert result.action == ActionType.PURSUE_NOW
        assert result.best_first_contact is not None

    def test_disqualified_account(self):
        score = self._make_score(is_disqualified=True, disqualify_reason="Too small")
        result = recommend_action(score, None, [])
        assert result.action == ActionType.DISQUALIFY

    def test_low_confidence_human_review(self):
        score = self._make_score(confidence_score=0.3)
        result = recommend_action(score, self._make_contact(), [self._make_pain()])
        assert result.action == ActionType.HUMAN_REVIEW_REQUIRED

    def test_decent_fit_weak_timing_nurture(self):
        score = self._make_score(
            icp_fit_score=60,
            timing_score=30,
            overall_priority_score=50,
            confidence_score=0.65,
        )
        result = recommend_action(score, self._make_contact(relevance=50), [self._make_pain(0.3)])
        assert result.action == ActionType.NURTURE

    def test_weak_fit_disqualify(self):
        score = self._make_score(icp_fit_score=20, overall_priority_score=25, confidence_score=0.6)
        result = recommend_action(score, None, [])
        assert result.action == ActionType.DISQUALIFY

    def test_no_contact_no_pain_human_review(self):
        score = self._make_score(overall_priority_score=55, confidence_score=0.6)
        result = recommend_action(score, None, [])
        # No contact meets threshold, should fall to human review or disqualify
        assert result.action in {ActionType.HUMAN_REVIEW_REQUIRED, ActionType.NURTURE, ActionType.DISQUALIFY}

    def test_multi_threading_recommended(self):
        result = recommend_action(
            self._make_score(overall_priority_score=80),
            self._make_contact(relevance=90),
            [self._make_pain(0.8), self._make_pain(0.6)],
        )
        assert result.action == ActionType.PURSUE_NOW
        assert result.multi_threading_recommended is True

    def test_threshold_details_populated(self):
        result = recommend_action(
            self._make_score(),
            self._make_contact(),
            [self._make_pain()],
        )
        assert "overall_priority_threshold" in result.threshold_details
        assert "overall_priority_actual" in result.threshold_details
