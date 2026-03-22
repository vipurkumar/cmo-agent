"""Report endpoint + ClickHouse queries for campaign analytics."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from clickhouse_driver import Client as SyncClickHouseClient
from fastapi import APIRouter

from src.api.deps import WorkspaceDep
from src.api.schemas import ReportRequest, ReportResponse
from src.config import settings
from src.logger import log

router = APIRouter()

# ---------------------------------------------------------------------------
# ClickHouse query helpers
# ---------------------------------------------------------------------------

_ch_client: SyncClickHouseClient | None = None


def _get_ch_client() -> SyncClickHouseClient:
    global _ch_client
    if _ch_client is None:
        _ch_client = SyncClickHouseClient.from_url(settings.CLICKHOUSE_URL)
    return _ch_client


async def _query_campaign_metrics(
    campaign_id: str,
    workspace_id: str,
    date_from: datetime,
    date_to: datetime,
) -> dict[str, Any]:
    """Query ClickHouse for aggregated campaign metrics.

    Runs synchronous clickhouse-driver in a thread pool.
    """

    def _run_query() -> list[tuple[Any, ...]]:
        client = _get_ch_client()
        return client.execute(
            """
            SELECT
                countIf(event_type = 'message_sent')   AS total_sent,
                countIf(event_type = 'reply')           AS total_replies,
                countIf(event_type = 'positive_reply')  AS positive_replies,
                countIf(event_type = 'open')            AS total_opens
            FROM session_events
            WHERE workspace_id = %(workspace_id)s
              AND metadata['campaign_id'] = %(campaign_id)s
              AND created_at >= %(date_from)s
              AND created_at <= %(date_to)s
            """,
            {
                "workspace_id": workspace_id,
                "campaign_id": campaign_id,
                "date_from": date_from,
                "date_to": date_to,
            },
        )

    rows = await asyncio.to_thread(_run_query)

    if not rows or not rows[0]:
        return {
            "total_sent": 0,
            "total_replies": 0,
            "positive_replies": 0,
            "total_opens": 0,
        }

    row = rows[0]
    return {
        "total_sent": row[0],
        "total_replies": row[1],
        "positive_replies": row[2],
        "total_opens": row[3],
    }


async def _query_campaign_cost(
    campaign_id: str,
    workspace_id: str,
    date_from: datetime,
    date_to: datetime,
) -> float:
    """Query ClickHouse for total LLM cost of a campaign."""

    def _run_query() -> list[tuple[Any, ...]]:
        client = _get_ch_client()
        return client.execute(
            """
            SELECT coalesce(sum(cost_usd), 0) AS total_cost
            FROM cost_events
            WHERE workspace_id = %(workspace_id)s
              AND created_at >= %(date_from)s
              AND created_at <= %(date_to)s
            """,
            {
                "workspace_id": workspace_id,
                "date_from": date_from,
                "date_to": date_to,
            },
        )

    rows = await asyncio.to_thread(_run_query)
    if not rows or not rows[0]:
        return 0.0
    return float(rows[0][0])


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/reports", response_model=ReportResponse)
async def generate_report(
    body: ReportRequest,
    workspace_id: WorkspaceDep,
):
    """Generate a campaign report with aggregated metrics from ClickHouse."""
    log.info(
        "api.generate_report",
        workspace_id=workspace_id,
        campaign_id=body.campaign_id,
        date_from=str(body.date_from),
        date_to=str(body.date_to),
    )

    metrics = await _query_campaign_metrics(
        campaign_id=body.campaign_id,
        workspace_id=workspace_id,
        date_from=body.date_from,
        date_to=body.date_to,
    )

    cost_usd = await _query_campaign_cost(
        campaign_id=body.campaign_id,
        workspace_id=workspace_id,
        date_from=body.date_from,
        date_to=body.date_to,
    )

    total_sent = metrics["total_sent"]
    total_replies = metrics["total_replies"]
    total_opens = metrics["total_opens"]

    open_rate = (total_opens / total_sent) if total_sent > 0 else 0.0
    reply_rate = (total_replies / total_sent) if total_sent > 0 else 0.0

    period = f"{body.date_from.strftime('%Y-%m-%d')} to {body.date_to.strftime('%Y-%m-%d')}"

    return ReportResponse(
        campaign_id=body.campaign_id,
        period=period,
        total_sent=total_sent,
        total_replies=total_replies,
        positive_replies=metrics["positive_replies"],
        open_rate=round(open_rate, 4),
        reply_rate=round(reply_rate, 4),
        cost_usd=round(cost_usd, 4),
    )
