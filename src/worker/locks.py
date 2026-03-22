"""Distributed thread locks using Redis SET NX EX.

Prevents two concurrent workers from resuming the same LangGraph thread
(e.g. when duplicate webhooks arrive).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from src.config import settings
from src.logger import log


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class ThreadLockError(Exception):
    """Raised when a distributed thread lock cannot be acquired."""


# ---------------------------------------------------------------------------
# Lock context manager
# ---------------------------------------------------------------------------
@asynccontextmanager
async def thread_lock(
    redis: Redis,
    thread_id: str,
    ttl: int = 30,
) -> AsyncIterator[None]:
    """Acquire a distributed lock for *thread_id*, auto-release on exit.

    Parameters
    ----------
    redis:
        Async Redis connection.
    thread_id:
        The LangGraph thread identifier to lock.  The Redis key is prefixed
        with the global key prefix **and** the thread_id already encodes its
        workspace, satisfying tenant-isolation rules.
    ttl:
        Lock time-to-live in seconds.  The lock auto-expires if the holder
        crashes, preventing deadlocks.

    Raises
    ------
    ThreadLockError
        If another worker already holds the lock.
    """
    key = f"{settings.REDIS_KEY_PREFIX}lock:thread:{thread_id}"
    # Unique value so only the holder can release it (prevents accidental
    # deletion by a different worker whose lock expired).
    token = uuid.uuid4().hex

    acquired = await redis.set(key, token, nx=True, ex=ttl)

    if not acquired:
        log.warning(
            "thread_lock.already_held",
            thread_id=thread_id,
            key=key,
        )
        raise ThreadLockError(
            f"Could not acquire lock for thread {thread_id}. "
            "Another worker is already processing this thread."
        )

    log.debug("thread_lock.acquired", thread_id=thread_id, ttl=ttl)

    try:
        yield
    finally:
        # Release only if we still own the lock (compare-and-delete via Lua).
        _release_lua = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        else
            return 0
        end
        """
        released = await redis.eval(_release_lua, 1, key, token)
        if released:
            log.debug("thread_lock.released", thread_id=thread_id)
        else:
            log.warning(
                "thread_lock.release_skipped",
                thread_id=thread_id,
                detail="Lock expired or was taken by another worker before release.",
            )
