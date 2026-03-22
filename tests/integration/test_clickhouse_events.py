"""ClickHouse analytics integration tests.

Requires: docker compose up -d (ClickHouse on port 9000)
Run with: uv run pytest tests/integration/ --integration -v

Tests event logging and query-back for qualification, recommendation,
feedback, and cost events in ClickHouse.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from src.db.clickhouse import ClickHouseClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_ws() -> str:
    """Generate a unique workspace_id for isolation."""
    return f"ws-ch-{uuid4().hex[:12]}"


async def _query_clickhouse(client: ClickHouseClient, query: str) -> list:
    """Run a SELECT query against ClickHouse via the sync client in a thread."""
    def _run():
        return client._get_client().execute(query)
    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# Qualification event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_qualification_event(clickhouse_client):
    """Log a qualification event, verify it can be queried back."""
    ws = _unique_ws()
    account_id = f"acct-{uuid4().hex[:8]}"

    await clickhouse_client.log_qualification_event(
        workspace_id=ws,
        account_id=account_id,
        event_type="account_scored",
        icp_fit_score=85,
        pain_fit_score=70,
        timing_score=60,
        overall_priority_score=72,
        action_type="pursue_now",
        confidence_score=0.82,
        scoring_version="v1",
        metadata={"source": "integration_test"},
    )

    # Query back
    rows = await _query_clickhouse(
        clickhouse_client,
        f"SELECT * FROM qualification_events WHERE workspace_id = '{ws}' "
        f"AND account_id = '{account_id}'",
    )

    assert len(rows) == 1
    row = rows[0]
    # Columns: id, workspace_id, account_id, event_type, icp_fit_score,
    #          pain_fit_score, timing_score, overall_priority_score,
    #          action_type, confidence_score, scoring_version, metadata, created_at
    assert row[1] == ws  # workspace_id
    assert row[2] == account_id  # account_id
    assert row[3] == "account_scored"  # event_type
    assert row[4] == 85  # icp_fit_score
    assert row[5] == 70  # pain_fit_score
    assert row[6] == 60  # timing_score
    assert row[7] == 72  # overall_priority_score
    assert row[8] == "pursue_now"  # action_type


# ---------------------------------------------------------------------------
# Recommendation event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_recommendation_event(clickhouse_client):
    """Log a recommendation event with all fields, verify persistence."""
    ws = _unique_ws()
    account_id = f"acct-{uuid4().hex[:8]}"
    brief_id = f"brief-{uuid4().hex[:8]}"

    await clickhouse_client.log_recommendation_event(
        workspace_id=ws,
        account_id=account_id,
        brief_id=brief_id,
        action_type="pursue_now",
        overall_score=82,
        confidence_score=0.78,
        contact_count=3,
        pain_count=2,
        signal_count=5,
        model_version="v1",
        prompt_version="v1",
        user_action="approved",
        metadata={"review_time_seconds": 45},
    )

    rows = await _query_clickhouse(
        clickhouse_client,
        f"SELECT * FROM recommendation_events WHERE workspace_id = '{ws}' "
        f"AND brief_id = '{brief_id}'",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row[1] == ws  # workspace_id
    assert row[3] == brief_id  # brief_id
    assert row[4] == "pursue_now"  # action_type
    assert row[5] == 82  # overall_score


# ---------------------------------------------------------------------------
# Feedback event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_feedback_event(clickhouse_client):
    """Log a feedback analytics event, verify persistence."""
    ws = _unique_ws()
    rec_id = f"rec-{uuid4().hex[:8]}"

    await clickhouse_client.log_feedback_event(
        workspace_id=ws,
        recommendation_id=rec_id,
        recommendation_type="seller_brief",
        user_id="user-ae-01",
        action_taken="approved_with_edits",
        model_version="v1",
    )

    rows = await _query_clickhouse(
        clickhouse_client,
        f"SELECT * FROM feedback_analytics WHERE workspace_id = '{ws}' "
        f"AND recommendation_id = '{rec_id}'",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row[1] == ws  # workspace_id
    assert row[2] == rec_id  # recommendation_id
    assert row[3] == "seller_brief"  # recommendation_type
    assert row[4] == "user-ae-01"  # user_id
    assert row[5] == "approved_with_edits"  # action_taken


# ---------------------------------------------------------------------------
# Cost event with workspace filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_cost_event(clickhouse_client):
    """Log a cost event, verify workspace_id filtering works."""
    ws_a = _unique_ws()
    ws_b = _unique_ws()

    # Log cost event for workspace A
    await clickhouse_client.log_cost_event(
        workspace_id=ws_a,
        task="email_generation",
        model="claude-sonnet-4-6",
        input_tokens=1500,
        output_tokens=800,
        cost_usd=0.012,
    )

    # Log cost event for workspace B
    await clickhouse_client.log_cost_event(
        workspace_id=ws_b,
        task="icp_scoring",
        model="claude-haiku-4-5-20251001",
        input_tokens=500,
        output_tokens=200,
        cost_usd=0.002,
    )

    # Query workspace A only
    rows_a = await _query_clickhouse(
        clickhouse_client,
        f"SELECT * FROM cost_events WHERE workspace_id = '{ws_a}'",
    )
    assert len(rows_a) == 1
    row_a = rows_a[0]
    assert row_a[1] == ws_a  # workspace_id
    assert row_a[2] == "email_generation"  # task

    # Query workspace B only
    rows_b = await _query_clickhouse(
        clickhouse_client,
        f"SELECT * FROM cost_events WHERE workspace_id = '{ws_b}'",
    )
    assert len(rows_b) == 1
    assert rows_b[0][1] == ws_b

    # Cross-workspace isolation: A should not see B's data
    rows_a_check = await _query_clickhouse(
        clickhouse_client,
        f"SELECT * FROM cost_events WHERE workspace_id = '{ws_a}' "
        f"AND task = 'icp_scoring'",
    )
    assert len(rows_a_check) == 0, "Workspace A should not see workspace B's cost events"


# ---------------------------------------------------------------------------
# Session event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_session_event(clickhouse_client):
    """Log a session event, verify it persists."""
    ws = _unique_ws()
    session_id = f"sess-{uuid4().hex[:8]}"

    await clickhouse_client.log_session_event(
        workspace_id=ws,
        session_id=session_id,
        event_type="qualification_started",
        metadata={"batch_size": 10, "trigger": "daily_batch"},
    )

    rows = await _query_clickhouse(
        clickhouse_client,
        f"SELECT * FROM session_events WHERE workspace_id = '{ws}' "
        f"AND session_id = '{session_id}'",
    )

    assert len(rows) == 1
    assert rows[0][1] == ws  # workspace_id
    assert rows[0][2] == session_id  # session_id
    assert rows[0][3] == "qualification_started"  # event_type


# ---------------------------------------------------------------------------
# Multiple qualification events for same account
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_qualification_events(clickhouse_client):
    """Log multiple qualification events for the same account, verify all persist."""
    ws = _unique_ws()
    account_id = f"acct-{uuid4().hex[:8]}"

    events = [
        ("account_scored", "pursue_now", 85),
        ("action_decided", "pursue_now", 85),
        ("brief_generated", "pursue_now", 82),
    ]

    for event_type, action_type, score in events:
        await clickhouse_client.log_qualification_event(
            workspace_id=ws,
            account_id=account_id,
            event_type=event_type,
            overall_priority_score=score,
            action_type=action_type,
            confidence_score=0.80,
        )

    rows = await _query_clickhouse(
        clickhouse_client,
        f"SELECT event_type FROM qualification_events "
        f"WHERE workspace_id = '{ws}' AND account_id = '{account_id}' "
        f"ORDER BY created_at",
    )

    assert len(rows) == 3
    event_types = [r[0] for r in rows]
    assert "account_scored" in event_types
    assert "action_decided" in event_types
    assert "brief_generated" in event_types
