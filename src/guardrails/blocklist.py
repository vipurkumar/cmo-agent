"""Domain, email, and company blocklist enforcement.

Backed by Redis sets for O(1) lookup. Auto-blocks unsubscribed contacts.
All keys are workspace-scoped.
"""

from __future__ import annotations

from src.config import settings
from src.config.automation import BLOCKLIST_CONFIG
from src.logger import log


class BlockedError(Exception):
    """Raised when a target is on a blocklist."""

    def __init__(self, target: str, blocklist_type: str) -> None:
        self.target = target
        self.blocklist_type = blocklist_type
        super().__init__(f"Blocked: {target} is on {blocklist_type} blocklist")


class BlocklistEnforcer:
    """Enforce domain/email/company blocklists via Redis sets."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._prefix = settings.REDIS_KEY_PREFIX

    def _key(self, workspace_id: str, blocklist_type: str) -> str:
        return f"{self._prefix}{workspace_id}:blocklist:{blocklist_type}"

    async def is_blocked(
        self,
        workspace_id: str,
        email: str | None = None,
        domain: str | None = None,
        company_name: str | None = None,
    ) -> tuple[bool, str | None]:
        """Check if a target is on any blocklist.

        Returns (is_blocked, reason) tuple.
        """
        config = BLOCKLIST_CONFIG

        if config["check_email_blocklist"] and email:
            email_key = self._key(workspace_id, "email")
            if await self._redis.sismember(email_key, email.lower()):
                return True, f"Email {email} is blocklisted"

        if config["check_domain_blocklist"] and domain:
            domain_key = self._key(workspace_id, "domain")
            if await self._redis.sismember(domain_key, domain.lower()):
                return True, f"Domain {domain} is blocklisted"

        if config["check_company_blocklist"] and company_name:
            company_key = self._key(workspace_id, "company")
            if await self._redis.sismember(company_key, company_name.lower()):
                return True, f"Company {company_name} is blocklisted"

        return False, None

    async def add_to_blocklist(
        self,
        workspace_id: str,
        blocklist_type: str,
        value: str,
        reason: str = "",
    ) -> None:
        """Add a value to a blocklist."""
        key = self._key(workspace_id, blocklist_type)
        await self._redis.sadd(key, value.lower())
        log.info(
            "blocklist.added",
            workspace_id=workspace_id,
            blocklist_type=blocklist_type,
            value=value,
            reason=reason,
        )

    async def remove_from_blocklist(
        self,
        workspace_id: str,
        blocklist_type: str,
        value: str,
    ) -> None:
        """Remove a value from a blocklist."""
        key = self._key(workspace_id, blocklist_type)
        await self._redis.srem(key, value.lower())
        log.info(
            "blocklist.removed",
            workspace_id=workspace_id,
            blocklist_type=blocklist_type,
            value=value,
        )

    async def auto_block_unsubscribed(
        self,
        workspace_id: str,
        email: str,
    ) -> None:
        """Auto-block an email after unsubscribe request."""
        if BLOCKLIST_CONFIG["auto_block_unsubscribed"]:
            await self.add_to_blocklist(
                workspace_id, "email", email, reason="unsubscribe"
            )

    async def list_blocklist(
        self,
        workspace_id: str,
        blocklist_type: str,
    ) -> set[str]:
        """List all entries in a blocklist."""
        key = self._key(workspace_id, blocklist_type)
        members = await self._redis.smembers(key)
        return {m.decode() if isinstance(m, bytes) else m for m in members}
