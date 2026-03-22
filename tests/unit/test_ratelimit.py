"""Tests for src/ratelimit/bucket.py — token bucket rate limiter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ratelimit.bucket import RATE_LIMITS, RateLimiter, RateLimitExceededError


class TestRateLimiter:
    @pytest.fixture(autouse=True)
    def _patch_settings(self, mock_settings):
        with patch("src.ratelimit.bucket.settings", mock_settings):
            yield

    @pytest.fixture()
    def limiter(self, mock_redis) -> RateLimiter:
        return RateLimiter(mock_redis)

    async def test_enforce_passes_when_under_limit(self, limiter):
        """When the Lua script returns remaining >= 0, enforce() passes silently."""
        # Script returns [remaining_tokens, retry_after]
        limiter._script = AsyncMock(return_value=[9, 0])

        await limiter.enforce(
            workspace_id="ws-test-001",
            resource="apollo",
            plan="pro",
        )
        # No exception raised — test passes

    async def test_enforce_raises_when_over_limit(self, limiter):
        """When the Lua script returns remaining < 0, raise RateLimitExceededError."""
        limiter._script = AsyncMock(return_value=[-1, 5])

        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.enforce(
                workspace_id="ws-test-001",
                resource="apollo",
                plan="pro",
            )

        assert exc_info.value.workspace_id == "ws-test-001"
        assert exc_info.value.resource == "apollo"
        assert exc_info.value.retry_after == 5

    async def test_unknown_resource_passes_silently(self, limiter):
        """Unknown resources log a warning but do not raise."""
        await limiter.enforce(
            workspace_id="ws-test-001",
            resource="nonexistent_api",
            plan="pro",
        )
        # No exception — unknown resources are allowed through with a warning

    async def test_unknown_plan_passes_silently(self, limiter):
        """Unknown plans for a known resource log a warning but do not raise."""
        await limiter.enforce(
            workspace_id="ws-test-001",
            resource="apollo",
            plan="nonexistent_plan",
        )
        # No exception

    async def test_script_called_with_correct_key(self, limiter, mock_settings):
        """Verify the Redis key uses the correct prefix and structure."""
        limiter._script = AsyncMock(return_value=[9, 0])

        await limiter.enforce(
            workspace_id="ws-123",
            resource="clay",
            plan="free",
        )

        # self._script(keys=[key], args=[...]) — keyword arguments
        call_kw = limiter._script.call_args.kwargs
        assert call_kw["keys"] == [f"{mock_settings.REDIS_KEY_PREFIX}ws-123:ratelimit:clay"]

    async def test_script_called_with_correct_limits(self, limiter):
        """Verify that max_tokens and refill_seconds from RATE_LIMITS are passed."""
        limiter._script = AsyncMock(return_value=[4, 0])

        await limiter.enforce(
            workspace_id="ws-test-001",
            resource="clay",
            plan="free",
        )

        call_kw = limiter._script.call_args.kwargs
        max_tokens, refill_seconds = RATE_LIMITS["clay"]["free"]
        assert call_kw["args"][0] == max_tokens
        assert call_kw["args"][1] == refill_seconds

    async def test_rate_limit_exceeded_message(self):
        """RateLimitExceededError has a descriptive message."""
        exc = RateLimitExceededError(
            workspace_id="ws-001",
            resource="apollo",
            retry_after=10,
        )
        assert "ws-001" in str(exc)
        assert "apollo" in str(exc)
        assert "10" in str(exc)
