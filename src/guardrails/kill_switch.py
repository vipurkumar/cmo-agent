"""Kill switch for OmniGTM automation.

Supports:
- Global pause (all workspaces)
- Per-workspace pause
- Auto-pause on high error/negative-reply rates
"""

from __future__ import annotations

from src.config import settings
from src.config.automation import KILL_SWITCH
from src.logger import log


class AutomationPausedError(Exception):
    """Raised when automation is paused."""

    def __init__(self, reason: str, scope: str = "global") -> None:
        self.reason = reason
        self.scope = scope
        super().__init__(f"Automation paused ({scope}): {reason}")


class KillSwitch:
    """Global and per-workspace automation kill switch backed by Redis."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._prefix = settings.REDIS_KEY_PREFIX

    def _global_key(self) -> str:
        return f"{self._prefix}automation:global_pause"

    def _workspace_key(self, workspace_id: str) -> str:
        return f"{self._prefix}{workspace_id}:automation:paused"

    def _workspace_reason_key(self, workspace_id: str) -> str:
        return f"{self._prefix}{workspace_id}:automation:pause_reason"

    async def is_paused(self, workspace_id: str) -> tuple[bool, str]:
        """Check if automation is paused globally or for a workspace.

        Returns (is_paused, reason).
        """
        # 1. Check global pause
        if KILL_SWITCH.get("global_pause"):
            return True, "Global automation pause is active (config)"

        global_val = await self._redis.get(self._global_key())
        if global_val:
            return True, "Global automation pause is active (Redis)"

        # 2. Check workspace pause
        ws_val = await self._redis.get(self._workspace_key(workspace_id))
        if ws_val:
            reason = await self._redis.get(self._workspace_reason_key(workspace_id))
            reason_str = reason.decode() if isinstance(reason, bytes) else (reason or "Manual pause")
            return True, f"Workspace paused: {reason_str}"

        return False, ""

    async def pause_global(self, reason: str = "Manual global pause") -> None:
        """Pause automation globally."""
        await self._redis.set(self._global_key(), reason)
        log.warning("kill_switch.global_pause", reason=reason)

    async def resume_global(self) -> None:
        """Resume global automation."""
        await self._redis.delete(self._global_key())
        log.info("kill_switch.global_resume")

    async def pause_workspace(
        self,
        workspace_id: str,
        reason: str = "Manual workspace pause",
    ) -> None:
        """Pause automation for a specific workspace."""
        await self._redis.set(self._workspace_key(workspace_id), "1")
        await self._redis.set(self._workspace_reason_key(workspace_id), reason)
        log.warning(
            "kill_switch.workspace_pause",
            workspace_id=workspace_id,
            reason=reason,
        )

    async def resume_workspace(self, workspace_id: str) -> None:
        """Resume automation for a specific workspace."""
        await self._redis.delete(self._workspace_key(workspace_id))
        await self._redis.delete(self._workspace_reason_key(workspace_id))
        log.info("kill_switch.workspace_resume", workspace_id=workspace_id)

    async def auto_pause_if_needed(
        self,
        workspace_id: str,
        error_count: int,
        total_sends: int,
        negative_reply_count: int,
        total_replies: int,
    ) -> bool:
        """Auto-pause workspace if error or negative reply rate exceeds thresholds.

        Returns True if auto-paused.
        """
        config = KILL_SWITCH

        # Check error rate
        if total_sends > 0:
            error_rate = error_count / total_sends
            if error_rate > config["pause_on_error_rate"]:
                reason = (
                    f"Auto-paused: error rate {error_rate:.1%} exceeds "
                    f"threshold {config['pause_on_error_rate']:.0%} "
                    f"({error_count}/{total_sends} sends)"
                )
                await self.pause_workspace(workspace_id, reason)
                return True

        # Check negative reply rate
        if total_replies > 0:
            negative_rate = negative_reply_count / total_replies
            if negative_rate > config["pause_on_negative_reply_rate"]:
                reason = (
                    f"Auto-paused: negative reply rate {negative_rate:.1%} exceeds "
                    f"threshold {config['pause_on_negative_reply_rate']:.0%} "
                    f"({negative_reply_count}/{total_replies} replies)"
                )
                await self.pause_workspace(workspace_id, reason)
                return True

        return False

    async def get_status(self, workspace_id: str) -> dict:
        """Get full automation status for a workspace."""
        paused, reason = await self.is_paused(workspace_id)
        return {
            "workspace_id": workspace_id,
            "is_paused": paused,
            "reason": reason,
            "global_pause": bool(await self._redis.get(self._global_key())),
            "workspace_pause": bool(
                await self._redis.get(self._workspace_key(workspace_id))
            ),
        }
