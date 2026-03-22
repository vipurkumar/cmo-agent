"""ClickHouse analytics writes.

Provides an async client for logging session events and LLM cost events
to ClickHouse for analytics dashboards and cost tracking.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from clickhouse_driver import Client as SyncClickHouseClient

from src.config import settings
from src.logger import log


class ClickHouseClient:
    """Async wrapper around clickhouse-driver for analytics writes.

    clickhouse-driver is synchronous, so we run inserts in a thread pool
    via asyncio.to_thread to keep the event loop unblocked.
    """

    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.CLICKHOUSE_URL
        self._client: SyncClickHouseClient | None = None

    def _get_client(self) -> SyncClickHouseClient:
        if self._client is None:
            self._client = SyncClickHouseClient.from_url(self._url)
        return self._client

    def _execute_sync(self, query: str, data: list[dict[str, Any]]) -> None:
        client = self._get_client()
        client.execute(query, data)

    async def _execute(self, query: str, data: list[dict[str, Any]]) -> None:
        await asyncio.to_thread(self._execute_sync, query, data)

    async def log_session_event(
        self,
        workspace_id: str,
        session_id: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log an agent session event to ClickHouse."""
        log.info(
            "clickhouse.log_session_event",
            workspace_id=workspace_id,
            session_id=session_id,
            event_type=event_type,
        )
        row = {
            "id": str(uuid4()),
            "workspace_id": workspace_id,
            "session_id": session_id,
            "event_type": event_type,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC),
        }
        await self._execute(
            "INSERT INTO session_events"
            " (id, workspace_id, session_id,"
            " event_type, metadata, created_at) VALUES",
            [row],
        )

    async def log_cost_event(
        self,
        workspace_id: str,
        task: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        """Log an LLM cost event to ClickHouse for budget tracking."""
        log.info(
            "clickhouse.log_cost_event",
            workspace_id=workspace_id,
            task=task,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        row = {
            "id": str(uuid4()),
            "workspace_id": workspace_id,
            "task": task,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "created_at": datetime.now(UTC),
        }
        await self._execute(
            "INSERT INTO cost_events"
            " (id, workspace_id, task, model,"
            " input_tokens, output_tokens,"
            " cost_usd, created_at) VALUES",
            [row],
        )

    # ------------------------------------------------------------------
    # OmniGTM qualification events
    # ------------------------------------------------------------------

    async def log_qualification_event(
        self,
        workspace_id: str,
        account_id: str,
        event_type: str,
        icp_fit_score: int = 0,
        pain_fit_score: int = 0,
        timing_score: int = 0,
        overall_priority_score: int = 0,
        action_type: str = "",
        confidence_score: float = 0.0,
        scoring_version: str = "v1",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log an account qualification event for analytics and audit."""
        log.info(
            "clickhouse.log_qualification_event",
            workspace_id=workspace_id,
            account_id=account_id,
            event_type=event_type,
            action_type=action_type,
        )
        row = {
            "id": str(uuid4()),
            "workspace_id": workspace_id,
            "account_id": account_id,
            "event_type": event_type,
            "icp_fit_score": icp_fit_score,
            "pain_fit_score": pain_fit_score,
            "timing_score": timing_score,
            "overall_priority_score": overall_priority_score,
            "action_type": action_type,
            "confidence_score": confidence_score,
            "scoring_version": scoring_version,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC),
        }
        await self._execute(
            "INSERT INTO qualification_events"
            " (id, workspace_id, account_id, event_type,"
            " icp_fit_score, pain_fit_score, timing_score,"
            " overall_priority_score, action_type,"
            " confidence_score, scoring_version,"
            " metadata, created_at) VALUES",
            [row],
        )

    async def log_recommendation_event(
        self,
        workspace_id: str,
        account_id: str,
        brief_id: str,
        action_type: str,
        overall_score: int,
        confidence_score: float,
        contact_count: int = 0,
        pain_count: int = 0,
        signal_count: int = 0,
        model_version: str = "v1",
        prompt_version: str = "v1",
        user_action: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a recommendation event (brief generated, feedback received)."""
        log.info(
            "clickhouse.log_recommendation_event",
            workspace_id=workspace_id,
            account_id=account_id,
            brief_id=brief_id,
            action_type=action_type,
        )
        row = {
            "id": str(uuid4()),
            "workspace_id": workspace_id,
            "account_id": account_id,
            "brief_id": brief_id,
            "action_type": action_type,
            "overall_score": overall_score,
            "confidence_score": confidence_score,
            "contact_count": contact_count,
            "pain_count": pain_count,
            "signal_count": signal_count,
            "model_version": model_version,
            "prompt_version": prompt_version,
            "user_action": user_action or "",
            "metadata": metadata or {},
            "created_at": datetime.now(UTC),
        }
        await self._execute(
            "INSERT INTO recommendation_events"
            " (id, workspace_id, account_id, brief_id,"
            " action_type, overall_score, confidence_score,"
            " contact_count, pain_count, signal_count,"
            " model_version, prompt_version,"
            " user_action, metadata, created_at) VALUES",
            [row],
        )

    async def log_feedback_event(
        self,
        workspace_id: str,
        recommendation_id: str,
        recommendation_type: str,
        user_id: str,
        action_taken: str,
        model_version: str = "v1",
    ) -> None:
        """Log a feedback event for offline learning analytics."""
        log.info(
            "clickhouse.log_feedback_event",
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            action_taken=action_taken,
        )
        row = {
            "id": str(uuid4()),
            "workspace_id": workspace_id,
            "recommendation_id": recommendation_id,
            "recommendation_type": recommendation_type,
            "user_id": user_id,
            "action_taken": action_taken,
            "model_version": model_version,
            "created_at": datetime.now(UTC),
        }
        await self._execute(
            "INSERT INTO feedback_analytics"
            " (id, workspace_id, recommendation_id,"
            " recommendation_type, user_id,"
            " action_taken, model_version, created_at) VALUES",
            [row],
        )
