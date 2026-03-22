"""Tests for worker runner and distributed locks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.worker.runner import SessionWorker, _process_job, register_handler


# ---------------------------------------------------------------------------
# register_handler
# ---------------------------------------------------------------------------


class TestRegisterHandler:
    def test_registers_handler(self):
        @register_handler("test_registration")
        async def handler(payload, workspace_id):
            return "ok"

        from src.worker.runner import _handlers

        assert "test_registration" in _handlers
        # Clean up
        del _handlers["test_registration"]


# ---------------------------------------------------------------------------
# _process_job
# ---------------------------------------------------------------------------


class TestProcessJob:
    async def test_dispatches_to_handler(self):
        handler = AsyncMock(return_value="result")
        with patch("src.worker.runner._handlers", {"my_job": handler}):
            job = MagicMock()
            job.data = {
                "job_type": "my_job",
                "workspace_id": "ws-001",
                "payload": {"key": "value"},
            }
            job.id = "job-123"
            job.name = "my_job"
            job.queueName = "batch"

            result = await _process_job(job, "token")
            assert result == "result"
            handler.assert_awaited_once_with({"key": "value"}, workspace_id="ws-001")

    async def test_raises_for_unknown_handler(self):
        with patch("src.worker.runner._handlers", {}):
            job = MagicMock()
            job.data = {
                "job_type": "unknown_job",
                "workspace_id": "ws-001",
                "payload": {},
            }
            job.id = "job-456"
            job.name = "unknown_job"
            job.queueName = "batch"

            with pytest.raises(ValueError, match="No handler"):
                await _process_job(job, "token")

    @patch("src.worker.runner.settings")
    async def test_acquires_thread_lock(self, mock_settings):
        mock_settings.REDIS_URL = "redis://localhost:6379/15"

        handler = AsyncMock(return_value="locked_result")
        mock_lock = AsyncMock()
        mock_lock.__aenter__ = AsyncMock()
        mock_lock.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.worker.runner._handlers", {"lock_job": handler}),
            patch("src.worker.runner.thread_lock", return_value=mock_lock),
            patch("src.worker.runner.Redis") as mock_redis_cls,
        ):
            mock_redis_instance = AsyncMock()
            mock_redis_cls.from_url.return_value = mock_redis_instance

            job = MagicMock()
            job.data = {
                "job_type": "lock_job",
                "workspace_id": "ws-001",
                "payload": {"thread_id": "thread-123", "key": "val"},
            }
            job.id = "job-789"
            job.name = "lock_job"
            job.queueName = "critical"

            result = await _process_job(job, "token")
            assert result == "locked_result"

    async def test_uses_job_name_fallback(self):
        handler = AsyncMock(return_value="ok")
        with patch("src.worker.runner._handlers", {"fallback_name": handler}):
            job = MagicMock()
            job.data = {"workspace_id": "ws-001", "payload": {}}  # no job_type
            job.id = "job-abc"
            job.name = "fallback_name"
            job.queueName = "batch"

            result = await _process_job(job, "token")
            assert result == "ok"


# ---------------------------------------------------------------------------
# SessionWorker
# ---------------------------------------------------------------------------


class TestSessionWorker:
    def test_request_shutdown_sets_event(self):
        worker = SessionWorker()
        assert not worker._shutdown_event.is_set()
        worker.request_shutdown()
        assert worker._shutdown_event.is_set()


# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------


class TestThreadLock:
    @patch("src.worker.locks.settings")
    async def test_lock_acquire_and_release(self, mock_settings):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock(return_value=1)

        from src.worker.locks import thread_lock

        async with thread_lock(mock_redis, "thread-001"):
            mock_redis.set.assert_called_once()

        mock_redis.delete.assert_called_once()

    @patch("src.worker.locks.settings")
    async def test_lock_raises_when_unavailable(self, mock_settings):
        mock_settings.REDIS_KEY_PREFIX = "cmo_test:"
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=False)  # Lock not acquired

        from src.worker.locks import ThreadLockError, thread_lock

        with pytest.raises(ThreadLockError):
            async with thread_lock(mock_redis, "thread-001"):
                pass  # Should not reach here
