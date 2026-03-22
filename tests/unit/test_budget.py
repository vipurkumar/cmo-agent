"""Tests for src/llm/budget.py — the central LLM gateway."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.budget import BUDGETS, MODEL_COSTS, calculate_cost


# ---------------------------------------------------------------------------
# calculate_cost
# ---------------------------------------------------------------------------


class TestCalculateCost:
    def test_sonnet_cost(self):
        cost = calculate_cost("claude-sonnet-4-6", input_tokens=1000, output_tokens=500)
        expected = (1000 * 3.00 / 1_000_000) + (500 * 15.00 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_haiku_cost(self):
        cost = calculate_cost("claude-haiku-4-5-20251001", input_tokens=1000, output_tokens=500)
        expected = (1000 * 0.80 / 1_000_000) + (500 * 4.00 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_zero_tokens(self):
        cost = calculate_cost("claude-sonnet-4-6", input_tokens=0, output_tokens=0)
        assert cost == 0.0

    def test_unknown_model_defaults_to_sonnet(self):
        """Models without 'haiku' in the name fall back to sonnet pricing."""
        cost = calculate_cost("claude-opus-5", input_tokens=1000, output_tokens=500)
        expected = (1000 * 3.00 / 1_000_000) + (500 * 15.00 / 1_000_000)
        assert cost == pytest.approx(expected)


# ---------------------------------------------------------------------------
# call_claude
# ---------------------------------------------------------------------------


class TestCallClaude:
    @pytest.fixture(autouse=True)
    def _patch_settings(self, mock_settings):
        with patch("src.llm.budget.settings", mock_settings):
            yield

    @pytest.fixture()
    def mock_anthropic_client(self):
        """Patch the singleton client inside budget.py."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Generated email body here.")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("src.llm.budget._client", mock_client):
            yield mock_client

    async def test_successful_call_returns_text(self, mock_anthropic_client):
        from src.llm.budget import call_claude

        result = await call_claude(
            task="email_generation",
            system="You are a copywriter.",
            user="Write an email.",
            workspace_id="ws-test-001",
        )
        assert result == "Generated email body here."
        mock_anthropic_client.messages.create.assert_awaited_once()

    async def test_uses_budget_max_tokens(self, mock_anthropic_client):
        from src.llm.budget import call_claude

        await call_claude(
            task="classification",
            system="Classify.",
            user="Is this positive?",
            workspace_id="ws-test-001",
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == BUDGETS["classification"]

    async def test_override_max_tokens(self, mock_anthropic_client):
        from src.llm.budget import call_claude

        await call_claude(
            task="email_generation",
            system="System.",
            user="User.",
            workspace_id="ws-test-001",
            max_tokens=2048,
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 2048

    async def test_unknown_task_uses_default_budget(self, mock_anthropic_client):
        """Unknown task keys fall back to 1024 tokens (not an error)."""
        from src.llm.budget import call_claude

        await call_claude(
            task="unknown_task_xyz",
            system="System.",
            user="User.",
            workspace_id="ws-test-001",
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 1024

    async def test_override_model(self, mock_anthropic_client, mock_settings):
        from src.llm.budget import call_claude

        await call_claude(
            task="classification",
            system="System.",
            user="User.",
            workspace_id="ws-test-001",
            model="claude-haiku-4-5-20251001",
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"

    async def test_default_model_from_settings(self, mock_anthropic_client, mock_settings):
        from src.llm.budget import call_claude

        await call_claude(
            task="email_generation",
            system="System.",
            user="User.",
            workspace_id="ws-test-001",
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == mock_settings.CLAUDE_MODEL
