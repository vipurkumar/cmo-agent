"""Tests for tools: ApolloSearchTool, ClayEnrichTool, ClaudeWriterTool.

Uses respx for HTTP mocking and AsyncMock for the rate limiter.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from src.tools.apollo_search import ApolloAuthError, ApolloRateLimitError, ApolloSearchTool
from src.tools.clay_enrich import ClayAuthError, ClayEnrichTool, ClayRateLimitError
from src.tools.claude_writer import ClaudeWriterTool


# ===========================================================================
# ApolloSearchTool
# ===========================================================================


class TestApolloSearchTool:
    @pytest.fixture(autouse=True)
    def _patch_settings(self, mock_settings):
        with patch("src.tools.apollo_search.settings", mock_settings):
            yield

    @pytest.fixture()
    def tool(self, mock_rate_limiter) -> ApolloSearchTool:
        return ApolloSearchTool(mock_rate_limiter)

    @respx.mock
    async def test_200_returns_contacts(self, tool, mock_settings):
        people = [{"name": "Jane Doe", "email": "jane@acme.com"}]
        respx.post(f"{mock_settings.APOLLO_BASE_URL}/mixed_people/search").mock(
            return_value=httpx.Response(200, json={"people": people})
        )

        result = await tool.run(
            query="Acme Corp",
            workspace_id="ws-test-001",
            plan="pro",
        )

        assert result == people
        tool.rate_limiter.enforce.assert_awaited_once_with("ws-test-001", "apollo", "pro")

    @respx.mock
    async def test_401_raises_auth_error(self, tool, mock_settings):
        respx.post(f"{mock_settings.APOLLO_BASE_URL}/mixed_people/search").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )

        with pytest.raises(ApolloAuthError):
            await tool.run(
                query="Acme Corp",
                workspace_id="ws-test-001",
                plan="pro",
            )

    @respx.mock
    async def test_429_raises_rate_limit_error(self, tool, mock_settings):
        respx.post(f"{mock_settings.APOLLO_BASE_URL}/mixed_people/search").mock(
            return_value=httpx.Response(429, json={"error": "Too many requests"})
        )

        with pytest.raises(ApolloRateLimitError):
            await tool.run(
                query="Acme Corp",
                workspace_id="ws-test-001",
                plan="pro",
            )

    @respx.mock
    async def test_empty_people_returns_empty_list(self, tool, mock_settings):
        respx.post(f"{mock_settings.APOLLO_BASE_URL}/mixed_people/search").mock(
            return_value=httpx.Response(200, json={"people": []})
        )

        result = await tool.run(
            query="Unknown Corp",
            workspace_id="ws-test-001",
            plan="pro",
        )
        assert result == []

    @respx.mock
    async def test_filters_passed_in_payload(self, tool, mock_settings):
        route = respx.post(f"{mock_settings.APOLLO_BASE_URL}/mixed_people/search").mock(
            return_value=httpx.Response(200, json={"people": []})
        )

        await tool.run(
            query="Acme Corp",
            workspace_id="ws-test-001",
            plan="pro",
            filters={"domain": "acme.com"},
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["domain"] == "acme.com"
        assert request_body["q"] == "Acme Corp"


# ===========================================================================
# ClayEnrichTool
# ===========================================================================


class TestClayEnrichTool:
    @pytest.fixture(autouse=True)
    def _patch_settings(self, mock_settings):
        with patch("src.tools.clay_enrich.settings", mock_settings):
            yield

    @pytest.fixture()
    def tool(self, mock_rate_limiter) -> ClayEnrichTool:
        return ClayEnrichTool(mock_rate_limiter)

    @respx.mock
    async def test_200_returns_enriched_data(self, tool, mock_settings):
        enriched = {"company": "Acme Corp", "funding": "$10M Series B"}
        respx.post(f"{mock_settings.CLAY_BASE_URL}/enrich").mock(
            return_value=httpx.Response(200, json=enriched)
        )

        result = await tool.run(
            identifier="jane@acme.com",
            workspace_id="ws-test-001",
            plan="pro",
        )

        assert result == enriched
        tool.rate_limiter.enforce.assert_awaited_once_with("ws-test-001", "clay", "pro")

    @respx.mock
    async def test_401_raises_auth_error(self, tool, mock_settings):
        respx.post(f"{mock_settings.CLAY_BASE_URL}/enrich").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )

        with pytest.raises(ClayAuthError):
            await tool.run(
                identifier="jane@acme.com",
                workspace_id="ws-test-001",
                plan="pro",
            )

    @respx.mock
    async def test_429_raises_rate_limit_error(self, tool, mock_settings):
        respx.post(f"{mock_settings.CLAY_BASE_URL}/enrich").mock(
            return_value=httpx.Response(429, json={"error": "Too many requests"})
        )

        with pytest.raises(ClayRateLimitError):
            await tool.run(
                identifier="jane@acme.com",
                workspace_id="ws-test-001",
                plan="pro",
            )

    @respx.mock
    async def test_domain_identifier_type(self, tool, mock_settings):
        route = respx.post(f"{mock_settings.CLAY_BASE_URL}/enrich").mock(
            return_value=httpx.Response(200, json={"domain": "acme.com"})
        )

        await tool.run(
            identifier="acme.com",
            workspace_id="ws-test-001",
            plan="pro",
            identifier_type="domain",
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body == {"domain": "acme.com"}


# ===========================================================================
# ClaudeWriterTool
# ===========================================================================


class TestClaudeWriterTool:
    @pytest.fixture(autouse=True)
    def _patch_settings(self, mock_settings):
        with patch("src.tools.claude_writer.settings", mock_settings):
            yield

    @pytest.fixture()
    def tool(self, mock_rate_limiter) -> ClaudeWriterTool:
        return ClaudeWriterTool(mock_rate_limiter)

    async def test_successful_generation(self, tool):
        email_json = json.dumps({
            "subject": "Quick question about your Series B",
            "body": "Hi Jane, I noticed Acme just closed a Series B...",
        })

        with patch("src.tools.claude_writer.call_claude", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = email_json

            result = await tool.run(
                research_data={"company": "Acme Corp", "funding": "$10M"},
                template="Hi {{first_name}}, {{hook}}...",
                personalization_hooks=["Series B momentum"],
                workspace_id="ws-test-001",
                plan="pro",
            )

        assert result["subject"] == "Quick question about your Series B"
        assert "Series B" in result["body"]
        tool.rate_limiter.enforce.assert_awaited_once_with("ws-test-001", "claude", "pro")

    async def test_json_parse_failure_uses_fallback(self, tool):
        """When Claude returns non-JSON, the tool falls back gracefully."""
        with patch("src.tools.claude_writer.call_claude", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "This is not valid JSON — just plain text."

            result = await tool.run(
                research_data={"company": "Acme"},
                template="Template",
                personalization_hooks=["hook1"],
                workspace_id="ws-test-001",
                plan="pro",
            )

        assert result["subject"] == "Follow-up"
        assert result["body"] == "This is not valid JSON — just plain text."

    async def test_call_claude_receives_correct_task(self, tool):
        """Verify call_claude is invoked with task='email_generation'."""
        email_json = json.dumps({"subject": "Hi", "body": "Hello"})

        with patch("src.tools.claude_writer.call_claude", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = email_json

            await tool.run(
                research_data={},
                template="t",
                personalization_hooks=[],
                workspace_id="ws-test-001",
                plan="pro",
            )

        mock_call.assert_awaited_once()
        assert mock_call.call_args.kwargs["task"] == "email_generation"
        assert mock_call.call_args.kwargs["workspace_id"] == "ws-test-001"
