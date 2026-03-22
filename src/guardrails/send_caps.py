"""Send cap enforcement for OmniGTM automation.

Tracks daily/weekly send counts per workspace and per account using Redis.
All keys are workspace-scoped and auto-expire.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.config import settings
from src.config.automation import SEND_CAPS
from src.logger import log


class SendCapError(Exception):
    """Raised when a send cap is exceeded."""

    def __init__(self, cap_type: str, current: int, limit: int) -> None:
        self.cap_type = cap_type
        self.current = current
        self.limit = limit
        super().__init__(
            f"Send cap exceeded: {cap_type} "
            f"(current={current}, limit={limit})"
        )


class SendCapEnforcer:
    """Enforce daily/weekly send caps per workspace using Redis."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._prefix = settings.REDIS_KEY_PREFIX

    def _key(self, workspace_id: str, scope: str, window: str) -> str:
        """Build a Redis key for a send counter."""
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        week = datetime.now(tz=timezone.utc).strftime("%Y-W%W")
        date_part = today if window == "daily" else week
        return f"{self._prefix}{workspace_id}:sendcap:{scope}:{window}:{date_part}"

    async def check_and_increment(
        self,
        workspace_id: str,
        account_id: str | None = None,
        caps: dict | None = None,
    ) -> None:
        """Check all send caps and increment counters if allowed.

        Raises SendCapError if any cap is exceeded.
        """
        caps = caps or SEND_CAPS

        # 1. Daily workspace cap
        daily_ws_key = self._key(workspace_id, "workspace", "daily")
        daily_count = int(await self._redis.get(daily_ws_key) or 0)
        daily_limit = caps["daily_max_per_workspace"]
        if daily_count >= daily_limit:
            log.warning(
                "sendcap.daily_workspace_exceeded",
                workspace_id=workspace_id,
                count=daily_count,
                limit=daily_limit,
            )
            raise SendCapError("daily_workspace", daily_count, daily_limit)

        # 2. Weekly workspace cap
        weekly_ws_key = self._key(workspace_id, "workspace", "weekly")
        weekly_count = int(await self._redis.get(weekly_ws_key) or 0)
        weekly_limit = caps["weekly_max_per_workspace"]
        if weekly_count >= weekly_limit:
            log.warning(
                "sendcap.weekly_workspace_exceeded",
                workspace_id=workspace_id,
                count=weekly_count,
                limit=weekly_limit,
            )
            raise SendCapError("weekly_workspace", weekly_count, weekly_limit)

        # 3. Daily per-account cap
        if account_id:
            daily_acct_key = self._key(workspace_id, f"account:{account_id}", "daily")
            acct_count = int(await self._redis.get(daily_acct_key) or 0)
            acct_limit = caps["daily_max_per_account"]
            if acct_count >= acct_limit:
                log.warning(
                    "sendcap.daily_account_exceeded",
                    workspace_id=workspace_id,
                    account_id=account_id,
                    count=acct_count,
                    limit=acct_limit,
                )
                raise SendCapError("daily_account", acct_count, acct_limit)

        # All caps OK — increment counters
        pipe = self._redis.pipeline()
        pipe.incr(daily_ws_key)
        pipe.expire(daily_ws_key, 86400 * 2)  # 2 days TTL
        pipe.incr(weekly_ws_key)
        pipe.expire(weekly_ws_key, 86400 * 8)  # 8 days TTL
        if account_id:
            daily_acct_key = self._key(workspace_id, f"account:{account_id}", "daily")
            pipe.incr(daily_acct_key)
            pipe.expire(daily_acct_key, 86400 * 2)
        await pipe.execute()

        log.info(
            "sendcap.incremented",
            workspace_id=workspace_id,
            account_id=account_id,
            daily_count=daily_count + 1,
        )

    async def get_remaining(
        self,
        workspace_id: str,
        caps: dict | None = None,
    ) -> dict[str, int]:
        """Get remaining send budget for a workspace."""
        caps = caps or SEND_CAPS
        daily_key = self._key(workspace_id, "workspace", "daily")
        weekly_key = self._key(workspace_id, "workspace", "weekly")

        daily_used = int(await self._redis.get(daily_key) or 0)
        weekly_used = int(await self._redis.get(weekly_key) or 0)

        return {
            "daily_remaining": max(0, caps["daily_max_per_workspace"] - daily_used),
            "weekly_remaining": max(0, caps["weekly_max_per_workspace"] - weekly_used),
            "daily_used": daily_used,
            "weekly_used": weekly_used,
        }
