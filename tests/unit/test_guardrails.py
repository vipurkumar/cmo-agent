"""Tests for guardrails — kill switch, send caps, blocklist."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.guardrails.blocklist import BlocklistEnforcer
from src.guardrails.kill_switch import KillSwitch
from src.guardrails.send_caps import SendCapEnforcer, SendCapError


# ---------------------------------------------------------------------------
# Test config overrides
# ---------------------------------------------------------------------------

TEST_KILL_SWITCH = {
    "global_pause": False,
    "pause_on_error_rate": 0.15,
    "pause_on_negative_reply_rate": 0.40,
}

TEST_SEND_CAPS = {
    "daily_max_per_workspace": 100,
    "weekly_max_per_workspace": 400,
    "daily_max_per_account": 3,
}

TEST_BLOCKLIST_CONFIG = {
    "check_email_blocklist": True,
    "check_domain_blocklist": True,
    "check_company_blocklist": True,
    "auto_block_unsubscribed": True,
}


@pytest.fixture()
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.sismember = AsyncMock(return_value=False)
    redis.sadd = AsyncMock(return_value=1)
    redis.srem = AsyncMock(return_value=1)
    redis.smembers = AsyncMock(return_value=set())
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    pipe = AsyncMock()
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[1, True, 1, True])
    redis.pipeline = MagicMock(return_value=pipe)
    return redis


# =========================================================================
# KillSwitch
# =========================================================================


class TestKillSwitch:
    @patch("src.guardrails.kill_switch.KILL_SWITCH", TEST_KILL_SWITCH)
    @patch("src.guardrails.kill_switch.settings")
    async def test_is_paused_returns_false_when_no_pause(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        ks = KillSwitch(mock_redis)
        paused, reason = await ks.is_paused("ws-001")
        assert paused is False
        assert reason == ""

    @patch("src.guardrails.kill_switch.KILL_SWITCH", {**TEST_KILL_SWITCH, "global_pause": True})
    @patch("src.guardrails.kill_switch.settings")
    async def test_is_paused_global_config(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        ks = KillSwitch(mock_redis)
        paused, reason = await ks.is_paused("ws-001")
        assert paused is True
        assert "config" in reason.lower() or "Global" in reason

    @patch("src.guardrails.kill_switch.KILL_SWITCH", TEST_KILL_SWITCH)
    @patch("src.guardrails.kill_switch.settings")
    async def test_is_paused_global_redis(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        mock_redis.get = AsyncMock(side_effect=lambda key: b"manual" if "global" in key else None)
        ks = KillSwitch(mock_redis)
        paused, reason = await ks.is_paused("ws-001")
        assert paused is True
        assert "Redis" in reason or "Global" in reason

    @patch("src.guardrails.kill_switch.KILL_SWITCH", TEST_KILL_SWITCH)
    @patch("src.guardrails.kill_switch.settings")
    async def test_is_paused_workspace(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"

        def side_effect(key):
            if "paused" in key and "reason" not in key:
                return b"1"
            if "reason" in key:
                return b"Too many errors"
            return None

        mock_redis.get = AsyncMock(side_effect=side_effect)
        ks = KillSwitch(mock_redis)
        paused, reason = await ks.is_paused("ws-001")
        assert paused is True
        assert "Too many errors" in reason

    @patch("src.guardrails.kill_switch.KILL_SWITCH", TEST_KILL_SWITCH)
    @patch("src.guardrails.kill_switch.settings")
    async def test_pause_global(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        ks = KillSwitch(mock_redis)
        await ks.pause_global("Test pause")
        mock_redis.set.assert_called_once()

    @patch("src.guardrails.kill_switch.KILL_SWITCH", TEST_KILL_SWITCH)
    @patch("src.guardrails.kill_switch.settings")
    async def test_resume_global(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        ks = KillSwitch(mock_redis)
        await ks.resume_global()
        mock_redis.delete.assert_called_once()

    @patch("src.guardrails.kill_switch.KILL_SWITCH", TEST_KILL_SWITCH)
    @patch("src.guardrails.kill_switch.settings")
    async def test_pause_workspace(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        ks = KillSwitch(mock_redis)
        await ks.pause_workspace("ws-001", "Manual pause")
        assert mock_redis.set.call_count == 2  # paused key + reason key

    @patch("src.guardrails.kill_switch.KILL_SWITCH", TEST_KILL_SWITCH)
    @patch("src.guardrails.kill_switch.settings")
    async def test_resume_workspace(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        ks = KillSwitch(mock_redis)
        await ks.resume_workspace("ws-001")
        assert mock_redis.delete.call_count == 2

    @patch("src.guardrails.kill_switch.KILL_SWITCH", TEST_KILL_SWITCH)
    @patch("src.guardrails.kill_switch.settings")
    async def test_auto_pause_high_error_rate(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        ks = KillSwitch(mock_redis)
        paused = await ks.auto_pause_if_needed("ws-001", error_count=20, total_sends=100, negative_reply_count=0, total_replies=50)
        assert paused is True

    @patch("src.guardrails.kill_switch.KILL_SWITCH", TEST_KILL_SWITCH)
    @patch("src.guardrails.kill_switch.settings")
    async def test_auto_pause_high_negative_rate(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        ks = KillSwitch(mock_redis)
        paused = await ks.auto_pause_if_needed("ws-001", error_count=0, total_sends=100, negative_reply_count=50, total_replies=100)
        assert paused is True

    @patch("src.guardrails.kill_switch.KILL_SWITCH", TEST_KILL_SWITCH)
    @patch("src.guardrails.kill_switch.settings")
    async def test_auto_pause_below_thresholds(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        ks = KillSwitch(mock_redis)
        paused = await ks.auto_pause_if_needed("ws-001", error_count=1, total_sends=100, negative_reply_count=5, total_replies=100)
        assert paused is False

    @patch("src.guardrails.kill_switch.KILL_SWITCH", TEST_KILL_SWITCH)
    @patch("src.guardrails.kill_switch.settings")
    async def test_get_status(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        ks = KillSwitch(mock_redis)
        status = await ks.get_status("ws-001")
        assert status["workspace_id"] == "ws-001"
        assert "is_paused" in status


# =========================================================================
# SendCapEnforcer
# =========================================================================


class TestSendCapEnforcer:
    @patch("src.guardrails.send_caps.settings")
    async def test_check_under_caps(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        enforcer = SendCapEnforcer(mock_redis)
        # Under all caps (default returns None/0)
        await enforcer.check_and_increment("ws-001", "acct-001", caps=TEST_SEND_CAPS)

    @patch("src.guardrails.send_caps.settings")
    async def test_daily_workspace_cap_exceeded(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        mock_redis.get = AsyncMock(return_value=b"100")
        enforcer = SendCapEnforcer(mock_redis)
        with pytest.raises(SendCapError) as exc_info:
            await enforcer.check_and_increment("ws-001", caps=TEST_SEND_CAPS)
        assert exc_info.value.cap_type == "daily_workspace"

    @patch("src.guardrails.send_caps.settings")
    async def test_weekly_workspace_cap_exceeded(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"

        call_count = 0

        async def side_effect(key):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"50"  # daily OK
            return b"400"  # weekly exceeded

        mock_redis.get = AsyncMock(side_effect=side_effect)
        enforcer = SendCapEnforcer(mock_redis)
        with pytest.raises(SendCapError) as exc_info:
            await enforcer.check_and_increment("ws-001", caps=TEST_SEND_CAPS)
        assert exc_info.value.cap_type == "weekly_workspace"

    @patch("src.guardrails.send_caps.settings")
    async def test_daily_account_cap_exceeded(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"

        call_count = 0

        async def side_effect(key):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return b"10"  # daily + weekly workspace OK
            return b"3"  # account exceeded

        mock_redis.get = AsyncMock(side_effect=side_effect)
        enforcer = SendCapEnforcer(mock_redis)
        with pytest.raises(SendCapError) as exc_info:
            await enforcer.check_and_increment("ws-001", "acct-001", caps=TEST_SEND_CAPS)
        assert exc_info.value.cap_type == "daily_account"

    @patch("src.guardrails.send_caps.settings")
    async def test_get_remaining(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        mock_redis.get = AsyncMock(return_value=b"25")
        enforcer = SendCapEnforcer(mock_redis)
        remaining = await enforcer.get_remaining("ws-001", caps=TEST_SEND_CAPS)
        assert remaining["daily_remaining"] == 75
        assert remaining["daily_used"] == 25


# =========================================================================
# BlocklistEnforcer
# =========================================================================


class TestBlocklistEnforcer:
    @patch("src.guardrails.blocklist.BLOCKLIST_CONFIG", TEST_BLOCKLIST_CONFIG)
    @patch("src.guardrails.blocklist.settings")
    async def test_not_blocked(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        bl = BlocklistEnforcer(mock_redis)
        blocked, reason = await bl.is_blocked("ws-001", email="test@acme.com")
        assert blocked is False
        assert reason is None

    @patch("src.guardrails.blocklist.BLOCKLIST_CONFIG", TEST_BLOCKLIST_CONFIG)
    @patch("src.guardrails.blocklist.settings")
    async def test_email_blocked(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        mock_redis.sismember = AsyncMock(return_value=True)
        bl = BlocklistEnforcer(mock_redis)
        blocked, reason = await bl.is_blocked("ws-001", email="blocked@evil.com")
        assert blocked is True
        assert "blocked@evil.com" in reason

    @patch("src.guardrails.blocklist.BLOCKLIST_CONFIG", TEST_BLOCKLIST_CONFIG)
    @patch("src.guardrails.blocklist.settings")
    async def test_domain_blocked(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        mock_redis.sismember = AsyncMock(side_effect=lambda k, v: "domain" in k)
        bl = BlocklistEnforcer(mock_redis)
        blocked, reason = await bl.is_blocked("ws-001", domain="evil.com")
        assert blocked is True
        assert "evil.com" in reason

    @patch("src.guardrails.blocklist.BLOCKLIST_CONFIG", TEST_BLOCKLIST_CONFIG)
    @patch("src.guardrails.blocklist.settings")
    async def test_company_blocked(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        mock_redis.sismember = AsyncMock(side_effect=lambda k, v: "company" in k)
        bl = BlocklistEnforcer(mock_redis)
        blocked, reason = await bl.is_blocked("ws-001", company_name="Evil Corp")
        assert blocked is True
        assert "Evil Corp" in reason

    @patch("src.guardrails.blocklist.BLOCKLIST_CONFIG", TEST_BLOCKLIST_CONFIG)
    @patch("src.guardrails.blocklist.settings")
    async def test_add_to_blocklist(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        bl = BlocklistEnforcer(mock_redis)
        await bl.add_to_blocklist("ws-001", "email", "Test@Acme.com")
        mock_redis.sadd.assert_called_once()
        # Verify lowercased
        call_args = mock_redis.sadd.call_args
        assert call_args[0][1] == "test@acme.com"

    @patch("src.guardrails.blocklist.BLOCKLIST_CONFIG", TEST_BLOCKLIST_CONFIG)
    @patch("src.guardrails.blocklist.settings")
    async def test_remove_from_blocklist(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        bl = BlocklistEnforcer(mock_redis)
        await bl.remove_from_blocklist("ws-001", "email", "test@acme.com")
        mock_redis.srem.assert_called_once()

    @patch("src.guardrails.blocklist.BLOCKLIST_CONFIG", TEST_BLOCKLIST_CONFIG)
    @patch("src.guardrails.blocklist.settings")
    async def test_auto_block_unsubscribed(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        bl = BlocklistEnforcer(mock_redis)
        await bl.auto_block_unsubscribed("ws-001", "unsub@acme.com")
        mock_redis.sadd.assert_called_once()

    @patch(
        "src.guardrails.blocklist.BLOCKLIST_CONFIG",
        {**TEST_BLOCKLIST_CONFIG, "auto_block_unsubscribed": False},
    )
    @patch("src.guardrails.blocklist.settings")
    async def test_auto_block_disabled(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        bl = BlocklistEnforcer(mock_redis)
        await bl.auto_block_unsubscribed("ws-001", "unsub@acme.com")
        mock_redis.sadd.assert_not_called()

    @patch("src.guardrails.blocklist.BLOCKLIST_CONFIG", TEST_BLOCKLIST_CONFIG)
    @patch("src.guardrails.blocklist.settings")
    async def test_list_blocklist(self, mock_settings, mock_redis):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        mock_redis.smembers = AsyncMock(return_value={b"a@b.com", b"c@d.com"})
        bl = BlocklistEnforcer(mock_redis)
        members = await bl.list_blocklist("ws-001", "email")
        assert members == {"a@b.com", "c@d.com"}
