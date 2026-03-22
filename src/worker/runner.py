"""BullMQ worker that processes jobs from all CMO Agent queues.

Start via::

    python -m src.worker.runner

Each queue gets its own :class:`bullmq.Worker` instance with the concurrency
defined in :data:`src.worker.queues.QUEUE_CONFIG`.
"""

from __future__ import annotations

import asyncio
import signal
import time
from typing import Any

from bullmq import Job, Worker
from redis.asyncio import Redis

from src.config import settings
from src.logger import log
from src.observability.metrics import JOBS_TOTAL, JOB_DURATION, JOBS_IN_PROGRESS
from src.worker.locks import ThreadLockError, thread_lock
from src.worker.queues import QUEUE_CONFIG

# ---------------------------------------------------------------------------
# Job handler registry
# ---------------------------------------------------------------------------

# Maps job_type -> async callable(job_data) -> result.
# Populated by ``register_handler``.
_handlers: dict[str, Any] = {}


def register_handler(job_type: str):
    """Decorator that registers an async function as the handler for *job_type*."""

    def decorator(fn):
        _handlers[job_type] = fn
        return fn

    return decorator


# ---------------------------------------------------------------------------
# Core job processor
# ---------------------------------------------------------------------------


async def _process_job(job: Job, token: str) -> Any:
    """Entry-point called by every BullMQ worker for each job.

    1. Extracts metadata from ``job.data``.
    2. Acquires a distributed thread lock (if a ``thread_id`` is present).
    3. Dispatches to the registered handler for the ``job_type``.
    4. Logs start / complete / fail with structured fields.
    """
    data: dict[str, Any] = job.data or {}
    job_type: str = data.get("job_type", job.name)
    workspace_id: str = data.get("workspace_id", "unknown")
    payload: dict[str, Any] = data.get("payload", {})
    thread_id: str | None = payload.get("thread_id")

    queue_name: str = job.queueName if hasattr(job, "queueName") else "unknown"

    log_ctx = {
        "job_id": job.id,
        "job_type": job_type,
        "workspace_id": workspace_id,
        "queue": queue_name,
    }

    log.info("job.start", **log_ctx)
    start = time.monotonic()

    handler = _handlers.get(job_type)
    if handler is None:
        log.error("job.no_handler", **log_ctx)
        raise ValueError(f"No handler registered for job_type '{job_type}'")

    JOBS_IN_PROGRESS.labels(queue=queue_name).inc()
    try:
        # If the payload includes a thread_id we must acquire the distributed
        # lock before resuming a LangGraph thread (Architecture Rule #6).
        if thread_id:
            redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                async with thread_lock(redis, thread_id):
                    result = await handler(payload, workspace_id=workspace_id)
            finally:
                await redis.aclose()
        else:
            result = await handler(payload, workspace_id=workspace_id)

        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        log.info("job.complete", elapsed_ms=elapsed_ms, **log_ctx)
        JOBS_TOTAL.labels(job_type=job_type, queue=queue_name, status="complete").inc()
        JOB_DURATION.labels(job_type=job_type, queue=queue_name).observe(elapsed_ms / 1000)
        return result

    except ThreadLockError:
        # Another worker is already processing this thread — let BullMQ
        # retry via its built-in mechanism.
        log.warning("job.lock_conflict", thread_id=thread_id, **log_ctx)
        JOBS_TOTAL.labels(job_type=job_type, queue=queue_name, status="failed").inc()
        raise

    except Exception:
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        log.exception("job.failed", elapsed_ms=elapsed_ms, **log_ctx)
        JOBS_TOTAL.labels(job_type=job_type, queue=queue_name, status="failed").inc()
        JOB_DURATION.labels(job_type=job_type, queue=queue_name).observe(elapsed_ms / 1000)
        raise

    finally:
        JOBS_IN_PROGRESS.labels(queue=queue_name).dec()


# ---------------------------------------------------------------------------
# SessionWorker — manages one BullMQ Worker per queue
# ---------------------------------------------------------------------------


class SessionWorker:
    """Creates and manages a :class:`bullmq.Worker` for each queue in
    :data:`QUEUE_CONFIG`.

    Usage::

        worker = SessionWorker()
        await worker.start()   # blocks until shutdown signal
        await worker.stop()
    """

    def __init__(self) -> None:
        self._workers: list[Worker] = []
        self._shutdown_event = asyncio.Event()

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Spin up one BullMQ Worker per queue and wait for a shutdown signal."""
        prefix = f"{settings.REDIS_KEY_PREFIX}bull"

        for queue_name, cfg in QUEUE_CONFIG.items():
            worker = Worker(
                name=queue_name,
                processor=_process_job,
                opts={
                    "connection": settings.REDIS_URL,
                    "prefix": prefix,
                    "concurrency": cfg["concurrency"],
                    "autorun": False,
                },
            )
            self._workers.append(worker)
            log.info(
                "worker.registered",
                queue=queue_name,
                concurrency=cfg["concurrency"],
            )

        # Start all workers (non-blocking — each runs its own event loop task)
        for w in self._workers:
            asyncio.ensure_future(w.run())

        log.info("worker.all_started", queues=list(QUEUE_CONFIG))

        # Block until we receive a shutdown signal
        await self._shutdown_event.wait()

    async def stop(self, force: bool = False) -> None:
        """Gracefully (or forcefully) shut down all workers."""
        log.info("worker.shutting_down", force=force)
        await asyncio.gather(
            *(w.close(force=force) for w in self._workers),
            return_exceptions=True,
        )
        self._workers.clear()
        log.info("worker.stopped")

    def request_shutdown(self) -> None:
        """Signal the worker to stop (called from signal handlers)."""
        self._shutdown_event.set()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


async def _main() -> None:
    worker = SessionWorker()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.request_shutdown)

    try:
        await worker.start()
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(_main())
