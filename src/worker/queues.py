"""BullMQ queue configuration, job routing, and enqueue helpers.

Queues are created lazily on first use and reuse Redis connections
derived from ``settings.REDIS_URL``.
"""

from __future__ import annotations

import uuid
from typing import Any

from bullmq import Queue

from src.config import settings
from src.logger import log

# ---------------------------------------------------------------------------
# Queue configuration
# ---------------------------------------------------------------------------

QUEUE_CONFIG: dict[str, dict[str, Any]] = {
    "critical": {"concurrency": 10},
    "interactive": {"concurrency": 5},
    "batch": {"concurrency": 20},
    "background": {"concurrency": 50},
}

# ---------------------------------------------------------------------------
# Event-type → queue routing (see CLAUDE.md "Queue Routing Reference")
# ---------------------------------------------------------------------------

EVENT_ROUTING: dict[str, str] = {
    # critical — latency-sensitive / compliance
    "approval_response": "critical",
    "positive_reply": "critical",
    "unsubscribe_request": "critical",
    # interactive — user-initiated
    "manual_trigger": "interactive",
    "report_request": "interactive",
    # batch — scheduled, latency-tolerant
    "daily_batch": "batch",
    "check_replies": "batch",
    # background — fire and forget
    "memory_update": "background",
    "crm_sync": "background",
    # OmniGTM qualification workflow
    "qualification_batch": "batch",
    "brief_to_outbound": "interactive",
    "brief_approval": "critical",
    "brief_review": "critical",
    # Scheduled jobs
    "daily_rescore": "batch",
    "signal_refresh": "batch",
    "brief_refresh": "background",
}

# ---------------------------------------------------------------------------
# Lazy queue registry
# ---------------------------------------------------------------------------

_queues: dict[str, Queue] = {}


def _get_queue(name: str) -> Queue:
    """Return (or create) the BullMQ :class:`Queue` for *name*."""
    if name not in QUEUE_CONFIG:
        raise ValueError(
            f"Unknown queue '{name}'. Valid queues: {list(QUEUE_CONFIG)}"
        )

    if name not in _queues:
        prefix = f"{settings.REDIS_KEY_PREFIX}bull"
        _queues[name] = Queue(
            name=name,
            opts={
                "connection": settings.REDIS_URL,
                "prefix": prefix,
            },
        )
        log.info("queue.created", queue=name, prefix=prefix)

    return _queues[name]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


async def enqueue(
    queue_name: str,
    job_type: str,
    payload: dict[str, Any],
    workspace_id: str,
) -> str:
    """Add a job to the named queue and return its ``job_id``.

    The *workspace_id* is embedded in both the job data (for handler use)
    and the job-id prefix (for observability in Redis).
    """
    queue = _get_queue(queue_name)

    job_id = f"{workspace_id}:{job_type}:{uuid.uuid4().hex[:12]}"

    job = await queue.add(
        name=job_type,
        data={
            "workspace_id": workspace_id,
            "job_type": job_type,
            "payload": payload,
        },
        opts={"jobId": job_id},
    )

    log.info(
        "queue.enqueued",
        queue=queue_name,
        job_type=job_type,
        job_id=job.id,
        workspace_id=workspace_id,
    )
    return job.id


async def enqueue_by_event(
    event_type: str,
    payload: dict[str, Any],
    workspace_id: str,
) -> str:
    """Route *event_type* to the correct queue via :data:`EVENT_ROUTING`,
    then enqueue.

    Raises :class:`ValueError` if the event type is unknown.
    """
    queue_name = EVENT_ROUTING.get(event_type)
    if queue_name is None:
        raise ValueError(
            f"Unknown event_type '{event_type}'. "
            f"Valid types: {list(EVENT_ROUTING)}"
        )

    return await enqueue(
        queue_name=queue_name,
        job_type=event_type,
        payload=payload,
        workspace_id=workspace_id,
    )


async def close_all() -> None:
    """Gracefully close every open queue connection."""
    for name, queue in _queues.items():
        log.info("queue.closing", queue=name)
        await queue.close()
    _queues.clear()
