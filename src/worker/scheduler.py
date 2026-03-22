"""Scheduled jobs for OmniGTM — daily re-scoring and signal refresh.

Runs as a background task via BullMQ repeatable jobs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.db.queries import (
    Account,
    AccountScoreRecord,
    SellerBriefRecord,
    async_session_factory,
)
from src.logger import log
from src.worker.queues import enqueue

# We import select here for DB queries within this module
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Scheduled job config
# ---------------------------------------------------------------------------

SCHEDULED_JOBS: dict[str, dict[str, str]] = {
    "daily_rescore": {"cron": "0 6 * * 1-5", "handler": "schedule_daily_rescore"},
    "signal_refresh": {"cron": "0 */4 * * *", "handler": "schedule_signal_refresh"},
    "brief_refresh": {"cron": "0 8 * * 1", "handler": "schedule_brief_refresh"},
}


# ---------------------------------------------------------------------------
# Scheduling functions
# ---------------------------------------------------------------------------


async def schedule_daily_rescore(workspace_id: str) -> str:
    """Enqueue a qualification_batch job for all active accounts in the workspace.

    Uses the "batch" queue.

    Returns
    -------
    str
        The enqueued job_id.
    """
    log.info("scheduler.daily_rescore.start", workspace_id=workspace_id)

    async with async_session_factory() as session:
        result = await session.execute(
            select(Account.id)
            .where(Account.workspace_id == workspace_id)
        )
        account_ids = [row[0] for row in result.all()]

    log.info(
        "scheduler.daily_rescore.accounts_found",
        workspace_id=workspace_id,
        account_count=len(account_ids),
    )

    job_id = await enqueue(
        queue_name="batch",
        job_type="qualification_batch",
        payload={"account_ids": account_ids},
        workspace_id=workspace_id,
    )

    log.info(
        "scheduler.daily_rescore.complete",
        workspace_id=workspace_id,
        job_id=job_id,
    )
    return job_id


async def schedule_signal_refresh(workspace_id: str) -> str:
    """Enqueue a job to re-run signal detection on all scored accounts.

    Checks for new signals since last scan.

    Returns
    -------
    str
        The enqueued job_id.
    """
    log.info("scheduler.signal_refresh.start", workspace_id=workspace_id)

    # Find all accounts that have been scored (i.e. have an AccountScoreRecord)
    async with async_session_factory() as session:
        result = await session.execute(
            select(AccountScoreRecord.account_id)
            .where(AccountScoreRecord.workspace_id == workspace_id)
            .distinct()
        )
        scored_account_ids = [row[0] for row in result.all()]

    log.info(
        "scheduler.signal_refresh.accounts_found",
        workspace_id=workspace_id,
        account_count=len(scored_account_ids),
    )

    job_id = await enqueue(
        queue_name="batch",
        job_type="signal_refresh",
        payload={"account_ids": scored_account_ids},
        workspace_id=workspace_id,
    )

    log.info(
        "scheduler.signal_refresh.complete",
        workspace_id=workspace_id,
        job_id=job_id,
    )
    return job_id


async def schedule_brief_refresh(
    workspace_id: str,
    max_age_days: int = 7,
) -> str:
    """Enqueue re-generation of briefs older than max_age_days.

    Returns
    -------
    str
        The enqueued job_id.
    """
    log.info(
        "scheduler.brief_refresh.start",
        workspace_id=workspace_id,
        max_age_days=max_age_days,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    async with async_session_factory() as session:
        result = await session.execute(
            select(SellerBriefRecord.account_id)
            .where(SellerBriefRecord.workspace_id == workspace_id)
            .where(SellerBriefRecord.generated_at < cutoff)
            .distinct()
        )
        stale_account_ids = [row[0] for row in result.all()]

    log.info(
        "scheduler.brief_refresh.stale_briefs_found",
        workspace_id=workspace_id,
        account_count=len(stale_account_ids),
    )

    job_id = await enqueue(
        queue_name="background",
        job_type="brief_refresh",
        payload={
            "account_ids": stale_account_ids,
            "max_age_days": max_age_days,
        },
        workspace_id=workspace_id,
    )

    log.info(
        "scheduler.brief_refresh.complete",
        workspace_id=workspace_id,
        job_id=job_id,
    )
    return job_id


# ---------------------------------------------------------------------------
# Registration — registers all scheduled jobs as BullMQ repeatable jobs
# ---------------------------------------------------------------------------


async def register_scheduled_jobs(workspace_id: str) -> None:
    """Register all SCHEDULED_JOBS as BullMQ repeatable jobs for the workspace.

    Each job is enqueued with BullMQ repeat options so the worker
    processes them on the configured cron schedule.
    """
    from bullmq import Queue

    from src.config import settings

    prefix = f"{settings.REDIS_KEY_PREFIX}bull"

    log.info(
        "scheduler.register.start",
        workspace_id=workspace_id,
        job_count=len(SCHEDULED_JOBS),
    )

    for job_name, job_config in SCHEDULED_JOBS.items():
        # Determine the correct queue from EVENT_ROUTING
        from src.worker.queues import EVENT_ROUTING

        queue_name = EVENT_ROUTING.get(job_name, "background")

        queue = Queue(
            name=queue_name,
            opts={
                "connection": settings.REDIS_URL,
                "prefix": prefix,
            },
        )

        try:
            await queue.add(
                name=job_name,
                data={
                    "workspace_id": workspace_id,
                    "job_type": job_name,
                    "payload": {},
                },
                opts={
                    "repeat": {
                        "pattern": job_config["cron"],
                    },
                    "jobId": f"{workspace_id}:{job_name}:repeatable",
                },
            )

            log.info(
                "scheduler.register.job_added",
                workspace_id=workspace_id,
                job_name=job_name,
                cron=job_config["cron"],
                queue=queue_name,
            )
        finally:
            await queue.close()

    log.info(
        "scheduler.register.complete",
        workspace_id=workspace_id,
    )
