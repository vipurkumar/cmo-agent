"""Demo infrastructure stubs — no Redis, no PostgreSQL, no ClickHouse needed."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock


class DemoRateLimiter:
    """No-op rate limiter — always allows."""

    async def enforce(self, workspace_id: str, resource: str, plan: str) -> None:
        pass


class _DemoSession:
    """Fake async session that accepts writes and returns plausible results."""

    def __init__(self) -> None:
        self._storage: dict[str, Any] = {}

    async def execute(self, *args: Any, **kwargs: Any) -> MagicMock:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        return mock_result

    def add(self, obj: Any) -> None:
        if hasattr(obj, "id") and not obj.id:
            obj.id = str(uuid.uuid4())

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> _DemoSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def begin(self) -> _DemoSession:
        return self


@asynccontextmanager
async def demo_session_factory():
    """Drop-in replacement for async_session_factory()."""
    session = _DemoSession()
    try:
        yield session
    finally:
        pass


async def demo_save_message(
    session: Any,
    workspace_id: str,
    contact_id: str,
    campaign_id: str,
    subject: str,
    body: str,
    stage: str,
) -> Any:
    """Drop-in for queries.save_message() — returns a mock with an id."""
    mock_msg = MagicMock()
    mock_msg.id = f"demo-msg-{uuid.uuid4().hex[:8]}"
    mock_msg.workspace_id = workspace_id
    mock_msg.contact_id = contact_id
    mock_msg.campaign_id = campaign_id
    mock_msg.subject = subject
    mock_msg.body = body
    mock_msg.stage = stage
    mock_msg.status = "sent"
    return mock_msg


async def demo_update_message_status(
    session: Any,
    message_id: str,
    workspace_id: str,
    status: str,
) -> None:
    """Drop-in for queries.update_message_status()."""
    pass


async def demo_store_embedding(
    session: Any,
    workspace_id: str,
    campaign_id: str,
    content: str,
    embedding_vector: list[float],
) -> None:
    """Drop-in for campaign_memory.store_embedding()."""
    pass
