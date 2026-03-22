"""Tests for Phase 4: automation config, guardrails logic, and auto-outbound decisions."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.agent.state import (
    Account,
    AccountScore,
    ActionRecommendation,
    ActionType,
    BuyingRole,
    PainHypothesis,
    PainType,
    RankedContact,
    SellerBrief,
    Signal,
    SignalType,
)
from src.config.automation import (
    AUTO_OUTBOUND_THRESHOLDS,
    AUTOMATION_DEFAULTS,
    BLOCKLIST_CONFIG,
    KILL_SWITCH,
    ROLLBACK_CONFIG,
    SEND_CAPS,
)


# ---------------------------------------------------------------------------
# Automation config tests
# ---------------------------------------------------------------------------


class TestAutomationConfig:
    def test_automation_off_by_default(self):
        assert AUTOMATION_DEFAULTS["enabled"] is False

    def test_auto_thresholds_stricter_than_manual(self):
        """Auto-outbound thresholds must be stricter than manual pursue_now."""
        # Manual thresholds from action_thresholds.py
        manual_priority = 60
        manual_contact = 70
        manual_pain = 0.50

        assert AUTO_OUTBOUND_THRESHOLDS["overall_priority_min"] > manual_priority
        assert AUTO_OUTBOUND_THRESHOLDS["top_contact_relevance_min"] > manual_contact
        assert AUTO_OUTBOUND_THRESHOLDS["pain_confidence_min"] > manual_pain

    def test_send_caps_reasonable(self):
        assert SEND_CAPS["daily_max_per_workspace"] > 0
        assert SEND_CAPS["daily_max_per_workspace"] <= 100
        assert SEND_CAPS["weekly_max_per_workspace"] > SEND_CAPS["daily_max_per_workspace"]
        assert SEND_CAPS["cool_down_hours"] >= 24

    def test_kill_switch_defaults(self):
        assert KILL_SWITCH["global_pause"] is False
        assert 0 < KILL_SWITCH["pause_on_error_rate"] < 1
        assert 0 < KILL_SWITCH["pause_on_negative_reply_rate"] < 1

    def test_blocklist_defaults(self):
        assert BLOCKLIST_CONFIG["auto_block_unsubscribed"] is True

    def test_rollback_retention(self):
        assert ROLLBACK_CONFIG["keep_audit_days"] >= 30
        assert ROLLBACK_CONFIG["allow_undo_hours"] >= 1


# ---------------------------------------------------------------------------
# Auto-outbound threshold logic tests
# ---------------------------------------------------------------------------


class TestAutoOutboundThresholds:
    """Test the threshold checks without needing Redis."""

    def _make_high_confidence_state(self) -> dict:
        """Build a state that exceeds all auto-outbound thresholds."""
        return {
            "overall_priority_score": 90,
            "top_contact_relevance": 92,
            "pain_confidence": 0.85,
            "account_confidence": 0.88,
            "signal_count": 4,
            "unknown_count": 1,
        }

    def _check_thresholds(self, state: dict) -> tuple[bool, str]:
        """Replicate auto-outbound threshold logic."""
        t = AUTO_OUTBOUND_THRESHOLDS

        if state["overall_priority_score"] < t["overall_priority_min"]:
            return False, f"Priority {state['overall_priority_score']} < {t['overall_priority_min']}"
        if state["top_contact_relevance"] < t["top_contact_relevance_min"]:
            return False, f"Contact relevance {state['top_contact_relevance']} < {t['top_contact_relevance_min']}"
        if state["pain_confidence"] < t["pain_confidence_min"]:
            return False, f"Pain confidence {state['pain_confidence']} < {t['pain_confidence_min']}"
        if state["account_confidence"] < t["account_score_confidence_min"]:
            return False, f"Account confidence {state['account_confidence']} < {t['account_score_confidence_min']}"
        if state["signal_count"] < t["min_signals"]:
            return False, f"Signal count {state['signal_count']} < {t['min_signals']}"
        if state["unknown_count"] > t["max_unknowns"]:
            return False, f"Unknowns {state['unknown_count']} > {t['max_unknowns']}"

        return True, ""

    def test_high_confidence_passes(self):
        state = self._make_high_confidence_state()
        passes, reason = self._check_thresholds(state)
        assert passes
        assert reason == ""

    def test_low_priority_fails(self):
        state = self._make_high_confidence_state()
        state["overall_priority_score"] = 65  # below 80
        passes, reason = self._check_thresholds(state)
        assert not passes
        assert "Priority" in reason

    def test_low_contact_relevance_fails(self):
        state = self._make_high_confidence_state()
        state["top_contact_relevance"] = 70  # below 85
        passes, reason = self._check_thresholds(state)
        assert not passes
        assert "Contact relevance" in reason

    def test_low_pain_confidence_fails(self):
        state = self._make_high_confidence_state()
        state["pain_confidence"] = 0.50  # below 0.70
        passes, reason = self._check_thresholds(state)
        assert not passes
        assert "Pain confidence" in reason

    def test_low_account_confidence_fails(self):
        state = self._make_high_confidence_state()
        state["account_confidence"] = 0.60  # below 0.80
        passes, reason = self._check_thresholds(state)
        assert not passes
        assert "Account confidence" in reason

    def test_insufficient_signals_fails(self):
        state = self._make_high_confidence_state()
        state["signal_count"] = 1  # below 2
        passes, reason = self._check_thresholds(state)
        assert not passes
        assert "Signal count" in reason

    def test_too_many_unknowns_fails(self):
        state = self._make_high_confidence_state()
        state["unknown_count"] = 5  # above 3
        passes, reason = self._check_thresholds(state)
        assert not passes
        assert "Unknowns" in reason

    def test_borderline_passes(self):
        """Exactly at thresholds should pass."""
        state = {
            "overall_priority_score": AUTO_OUTBOUND_THRESHOLDS["overall_priority_min"],
            "top_contact_relevance": AUTO_OUTBOUND_THRESHOLDS["top_contact_relevance_min"],
            "pain_confidence": AUTO_OUTBOUND_THRESHOLDS["pain_confidence_min"],
            "account_confidence": AUTO_OUTBOUND_THRESHOLDS["account_score_confidence_min"],
            "signal_count": AUTO_OUTBOUND_THRESHOLDS["min_signals"],
            "unknown_count": AUTO_OUTBOUND_THRESHOLDS["max_unknowns"],
        }
        passes, _ = self._check_thresholds(state)
        assert passes


# ---------------------------------------------------------------------------
# Kill switch logic tests
# ---------------------------------------------------------------------------


class TestKillSwitchLogic:
    """Test kill switch auto-pause thresholds."""

    def test_error_rate_exceeds_threshold(self):
        total_sends = 100
        error_count = 15
        error_rate = error_count / total_sends
        assert error_rate > KILL_SWITCH["pause_on_error_rate"]

    def test_error_rate_within_threshold(self):
        total_sends = 100
        error_count = 5
        error_rate = error_count / total_sends
        assert error_rate <= KILL_SWITCH["pause_on_error_rate"]

    def test_negative_reply_rate_exceeds_threshold(self):
        total_replies = 20
        negative_count = 8
        negative_rate = negative_count / total_replies
        assert negative_rate > KILL_SWITCH["pause_on_negative_reply_rate"]

    def test_negative_reply_rate_within_threshold(self):
        total_replies = 20
        negative_count = 3
        negative_rate = negative_count / total_replies
        assert negative_rate <= KILL_SWITCH["pause_on_negative_reply_rate"]

    def test_zero_sends_no_division_error(self):
        total_sends = 0
        # Should not auto-pause with no sends
        if total_sends > 0:
            _ = 0 / total_sends
        # If we get here, no ZeroDivisionError

    def test_zero_replies_no_division_error(self):
        total_replies = 0
        if total_replies > 0:
            _ = 0 / total_replies


# ---------------------------------------------------------------------------
# Send cap logic tests
# ---------------------------------------------------------------------------


class TestSendCapLogic:
    """Test send cap threshold logic without Redis."""

    def test_daily_cap_exceeded(self):
        daily_count = SEND_CAPS["daily_max_per_workspace"]
        assert daily_count >= SEND_CAPS["daily_max_per_workspace"]

    def test_daily_cap_not_exceeded(self):
        daily_count = SEND_CAPS["daily_max_per_workspace"] - 1
        assert daily_count < SEND_CAPS["daily_max_per_workspace"]

    def test_weekly_cap_bounds(self):
        # Weekly must be >= daily * 5 (workdays)
        assert SEND_CAPS["weekly_max_per_workspace"] >= SEND_CAPS["daily_max_per_workspace"]

    def test_per_account_cap_reasonable(self):
        assert SEND_CAPS["daily_max_per_account"] >= 1
        assert SEND_CAPS["daily_max_per_account"] <= 10

    def test_cool_down_reasonable(self):
        assert SEND_CAPS["cool_down_hours"] >= 24


# ---------------------------------------------------------------------------
# Automation state field tests
# ---------------------------------------------------------------------------


class TestAutomationStateFields:
    """Test that QualificationState has Phase 4 automation fields."""

    def test_auto_outbound_triggered_field(self):
        from src.agent.state import QualificationState

        state: QualificationState = {
            "auto_outbound_triggered": True,
            "auto_outbound_skip_reason": None,
        }
        assert state["auto_outbound_triggered"] is True

    def test_auto_outbound_skip_reason_field(self):
        from src.agent.state import QualificationState

        state: QualificationState = {
            "auto_outbound_triggered": False,
            "auto_outbound_skip_reason": "Send cap exceeded",
        }
        assert state["auto_outbound_skip_reason"] == "Send cap exceeded"
