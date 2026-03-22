"""Token bucket rate limiter backed by a Redis Lua script.

Each workspace+resource pair gets an independent bucket. The Lua script
performs an atomic check-and-decrement so concurrent requests never
over-consume tokens.
"""

from __future__ import annotations

from redis.asyncio import Redis

from src.config import settings
from src.logger import log

# ---------------------------------------------------------------------------
# Per-resource, per-plan limits: (max_tokens, refill_seconds)
# ---------------------------------------------------------------------------
RATE_LIMITS: dict[str, dict[str, tuple[int, int]]] = {
    "apollo": {
        "free": (10, 60),
        "pro": (100, 60),
        "enterprise": (500, 60),
    },
    "clay": {
        "free": (5, 60),
        "pro": (50, 60),
        "enterprise": (200, 60),
    },
    "linkedin": {
        "free": (5, 60),
        "pro": (30, 60),
        "enterprise": (120, 60),
    },
    "email_send": {
        "free": (20, 60),
        "pro": (200, 60),
        "enterprise": (1000, 60),
    },
    "claude": {
        "free": (15, 60),
        "pro": (150, 60),
        "enterprise": (600, 60),
    },
}

# ---------------------------------------------------------------------------
# Lua script — atomic token bucket check-and-decrement
#
# KEYS[1] = bucket key
# ARGV[1] = max_tokens
# ARGV[2] = refill_seconds
# ARGV[3] = current epoch time (seconds)
#
# Returns remaining tokens (>= 0) on success, or -1 when the bucket is
# exhausted together with the TTL (seconds until a token is available).
# ---------------------------------------------------------------------------
_LUA_SCRIPT = """
local key          = KEYS[1]
local max_tokens   = tonumber(ARGV[1])
local refill_secs  = tonumber(ARGV[2])
local now          = tonumber(ARGV[3])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens      = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    -- First request: initialise the bucket with max_tokens - 1
    redis.call('HMSET', key, 'tokens', max_tokens - 1, 'last_refill', now)
    redis.call('EXPIRE', key, refill_secs * 2)
    return {max_tokens - 1, 0}
end

-- Refill tokens based on elapsed time
local elapsed       = now - last_refill
local refill_rate   = max_tokens / refill_secs
local new_tokens    = math.min(max_tokens, tokens + elapsed * refill_rate)
local updated_time  = now

if new_tokens >= 1 then
    new_tokens = new_tokens - 1
    redis.call('HMSET', key, 'tokens', new_tokens, 'last_refill', updated_time)
    redis.call('EXPIRE', key, refill_secs * 2)
    return {math.floor(new_tokens), 0}
else
    -- Not enough tokens — compute retry_after
    local deficit     = 1 - new_tokens
    local retry_after = math.ceil(deficit / refill_rate)
    redis.call('HMSET', key, 'tokens', new_tokens, 'last_refill', updated_time)
    redis.call('EXPIRE', key, refill_secs * 2)
    return {-1, retry_after}
end
"""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class RateLimitExceededError(Exception):
    """Raised when a workspace exceeds its rate limit for a resource."""

    def __init__(self, workspace_id: str, resource: str, retry_after: int) -> None:
        self.workspace_id = workspace_id
        self.resource = resource
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded for workspace {workspace_id} "
            f"on resource {resource}. Retry after {retry_after}s."
        )


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
class RateLimiter:
    """Token-bucket rate limiter using Redis for distributed state."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._script = self._redis.register_script(_LUA_SCRIPT)

    async def enforce(
        self,
        workspace_id: str,
        resource: str,
        plan: str,
    ) -> None:
        """Consume one token or raise :class:`RateLimitExceededError`.

        Parameters
        ----------
        workspace_id:
            Tenant identifier (used as Redis key prefix).
        resource:
            API / resource name (must exist in ``RATE_LIMITS``).
        plan:
            Billing plan of the workspace (``free``, ``pro``, ``enterprise``).
        """
        resource_limits = RATE_LIMITS.get(resource)
        if resource_limits is None:
            log.warning(
                "ratelimit.unknown_resource",
                resource=resource,
                workspace_id=workspace_id,
            )
            return

        plan_limit = resource_limits.get(plan)
        if plan_limit is None:
            log.warning(
                "ratelimit.unknown_plan",
                plan=plan,
                resource=resource,
                workspace_id=workspace_id,
            )
            return

        max_tokens, refill_seconds = plan_limit

        key = f"{settings.REDIS_KEY_PREFIX}{workspace_id}:ratelimit:{resource}"

        import time

        now = int(time.time())

        result = await self._script(
            keys=[key],
            args=[max_tokens, refill_seconds, now],
        )

        remaining, retry_after = int(result[0]), int(result[1])

        if remaining < 0:
            log.warning(
                "ratelimit.exceeded",
                workspace_id=workspace_id,
                resource=resource,
                plan=plan,
                retry_after=retry_after,
            )
            raise RateLimitExceededError(
                workspace_id=workspace_id,
                resource=resource,
                retry_after=retry_after,
            )

        log.debug(
            "ratelimit.ok",
            workspace_id=workspace_id,
            resource=resource,
            remaining=remaining,
        )
