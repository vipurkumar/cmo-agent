"""Tests for src/worker/queues.py — queue config, routing, enqueue helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.worker.queues import EVENT_ROUTING, QUEUE_CONFIG, _get_queue, enqueue, enqueue_by_event


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_queue_registry():
    """Clear the module-level queue cache between tests."""
    from src.worker import queues as queues_mod
    original = queues_mod._queues.copy()
    queues_mod._queues.clear()
    yield
    queues_mod._queues.clear()
    queues_mod._queues.update(original)


@pytest.fixture(autouse=True)
def _patch_settings(mock_settings):
    with patch("src.worker.queues.settings", mock_settings):
        yield


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


class TestEnqueue:
    async def test_enqueue_creates_job_with_correct_queue(self):
        mock_job = MagicMock()
        mock_job.id = "ws-test-001:daily_batch:abc123"

        mock_queue = MagicMock()
        mock_queue.add = AsyncMock(return_value=mock_job)

        with patch("src.worker.queues._get_queue", return_value=mock_queue):
            job_id = await enqueue(
                queue_name="batch",
                job_type="daily_batch",
                payload={"campaign_id": "camp-001"},
                workspace_id="ws-test-001",
            )

        assert job_id == mock_job.id
        mock_queue.add.assert_awaited_once()

        # Verify the data passed to Queue.add(name, data, opts)
        call_args = mock_queue.add.call_args
        # queue.add is called with positional: name, data + keyword: opts
        assert call_args.kwargs.get("name") or call_args[0][0] == "daily_batch"
        data = call_args.kwargs.get("data") or call_args[0][1]
        assert data["workspace_id"] == "ws-test-001"
        assert data["job_type"] == "daily_batch"
        assert data["payload"]["campaign_id"] == "camp-001"

    async def test_enqueue_invalid_queue_raises(self):
        with pytest.raises(ValueError, match="Unknown queue"):
            _get_queue("nonexistent_queue")


# ---------------------------------------------------------------------------
# enqueue_by_event
# ---------------------------------------------------------------------------


class TestEnqueueByEvent:
    @pytest.mark.parametrize(
        "event_type,expected_queue",
        [
            ("approval_response", "critical"),
            ("positive_reply", "critical"),
            ("unsubscribe_request", "critical"),
            ("manual_trigger", "interactive"),
            ("report_request", "interactive"),
            ("daily_batch", "batch"),
            ("check_replies", "batch"),
            ("memory_update", "background"),
            ("crm_sync", "background"),
        ],
    )
    async def test_routes_event_to_correct_queue(self, event_type, expected_queue):
        mock_job = MagicMock()
        mock_job.id = f"ws-001:{event_type}:abc123"

        mock_queue = MagicMock()
        mock_queue.add = AsyncMock(return_value=mock_job)

        with patch("src.worker.queues._get_queue", return_value=mock_queue) as mock_get_q:
            await enqueue_by_event(
                event_type=event_type,
                payload={"key": "value"},
                workspace_id="ws-001",
            )

            mock_get_q.assert_called_with(expected_queue)

    async def test_unknown_event_type_raises(self):
        with pytest.raises(ValueError, match="Unknown event_type"):
            await enqueue_by_event(
                event_type="totally_unknown_event",
                payload={},
                workspace_id="ws-001",
            )

    async def test_event_routing_matches_claude_md(self):
        """Verify EVENT_ROUTING contains all documented event types."""
        expected_events = {
            "approval_response",
            "positive_reply",
            "unsubscribe_request",
            "manual_trigger",
            "report_request",
            "daily_batch",
            "check_replies",
            "memory_update",
            "crm_sync",
        }
        assert set(EVENT_ROUTING.keys()) == expected_events


# ---------------------------------------------------------------------------
# QUEUE_CONFIG
# ---------------------------------------------------------------------------


class TestQueueConfig:
    def test_all_required_queues_defined(self):
        """All four queue tiers must exist."""
        assert "critical" in QUEUE_CONFIG
        assert "interactive" in QUEUE_CONFIG
        assert "batch" in QUEUE_CONFIG
        assert "background" in QUEUE_CONFIG

    def test_all_event_routes_point_to_valid_queues(self):
        """Every queue referenced in EVENT_ROUTING must exist in QUEUE_CONFIG."""
        for event_type, queue_name in EVENT_ROUTING.items():
            assert queue_name in QUEUE_CONFIG, (
                f"EVENT_ROUTING['{event_type}'] -> '{queue_name}' "
                f"not found in QUEUE_CONFIG"
            )
