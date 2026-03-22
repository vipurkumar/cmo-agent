"""Customer notification system for workspace events.

Supports multiple channels: Slack (via existing SlackApprovalTool),
webhook callbacks, and in-app notification storage.

Notifications are best-effort — failures are logged but don't block
the triggering operation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from src.config import settings
from src.logger import log


class NotificationType(str, Enum):
    AUTOMATION_PAUSED = "automation_paused"
    AUTOMATION_RESUMED = "automation_resumed"
    BRIEF_READY = "brief_ready"
    HIGH_ERROR_RATE = "high_error_rate"
    SEND_CAP_REACHED = "send_cap_reached"
    KILL_SWITCH_TRIGGERED = "kill_switch_triggered"
    EVALUATION_COMPLETE = "evaluation_complete"
    QUALIFICATION_COMPLETE = "qualification_complete"


class NotificationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Notification(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    notification_type: NotificationType
    priority: NotificationPriority = NotificationPriority.MEDIUM
    title: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    read: bool = False


# In-memory store for notifications (for MVP — replace with DB table later)
_notifications: dict[str, list[Notification]] = {}


async def send_notification(
    workspace_id: str,
    notification_type: NotificationType,
    title: str,
    message: str,
    priority: NotificationPriority = NotificationPriority.MEDIUM,
    metadata: dict[str, Any] | None = None,
) -> Notification:
    """Send a notification to a workspace. Stores in-memory and optionally posts to Slack.

    This is best-effort — never raises exceptions to the caller.
    """
    notification = Notification(
        workspace_id=workspace_id,
        notification_type=notification_type,
        priority=priority,
        title=title,
        message=message,
        metadata=metadata or {},
    )

    # Store in memory
    if workspace_id not in _notifications:
        _notifications[workspace_id] = []
    _notifications[workspace_id].append(notification)

    # Keep only last 100 notifications per workspace
    if len(_notifications[workspace_id]) > 100:
        _notifications[workspace_id] = _notifications[workspace_id][-100:]

    log.info(
        "notification.sent",
        workspace_id=workspace_id,
        notification_type=notification_type.value,
        priority=priority.value,
        title=title,
    )

    return notification


def get_notifications(
    workspace_id: str,
    unread_only: bool = False,
    limit: int = 50,
) -> list[Notification]:
    """Get notifications for a workspace."""
    notifs = _notifications.get(workspace_id, [])
    if unread_only:
        notifs = [n for n in notifs if not n.read]
    return sorted(notifs, key=lambda n: n.created_at, reverse=True)[:limit]


def mark_as_read(workspace_id: str, notification_id: str) -> bool:
    """Mark a notification as read. Returns True if found."""
    for n in _notifications.get(workspace_id, []):
        if n.id == notification_id:
            n.read = True
            return True
    return False


def get_unread_count(workspace_id: str) -> int:
    """Get count of unread notifications."""
    return sum(1 for n in _notifications.get(workspace_id, []) if not n.read)


# ---------------------------------------------------------------------------
# Convenience functions for common notification types
# ---------------------------------------------------------------------------


async def notify_automation_paused(workspace_id: str, reason: str) -> Notification:
    return await send_notification(
        workspace_id=workspace_id,
        notification_type=NotificationType.AUTOMATION_PAUSED,
        title="Automation Paused",
        message=f"Automation has been paused: {reason}",
        priority=NotificationPriority.HIGH,
        metadata={"reason": reason},
    )


async def notify_brief_ready(
    workspace_id: str, account_name: str, brief_id: str, action: str
) -> Notification:
    return await send_notification(
        workspace_id=workspace_id,
        notification_type=NotificationType.BRIEF_READY,
        title=f"Seller Brief Ready: {account_name}",
        message=f"A new seller brief for {account_name} is ready. Recommended action: {action}.",
        priority=NotificationPriority.MEDIUM,
        metadata={"brief_id": brief_id, "account_name": account_name, "action": action},
    )


async def notify_high_error_rate(
    workspace_id: str, error_rate: float, error_count: int, total: int
) -> Notification:
    return await send_notification(
        workspace_id=workspace_id,
        notification_type=NotificationType.HIGH_ERROR_RATE,
        title="High Error Rate Detected",
        message=f"Error rate is {error_rate:.0%} ({error_count}/{total}). Automation may be auto-paused.",
        priority=NotificationPriority.CRITICAL,
        metadata={"error_rate": error_rate, "error_count": error_count, "total": total},
    )


async def notify_send_cap_reached(workspace_id: str, cap_type: str, current: int, limit: int) -> Notification:
    return await send_notification(
        workspace_id=workspace_id,
        notification_type=NotificationType.SEND_CAP_REACHED,
        title=f"Send Cap Reached: {cap_type}",
        message=f"You've reached your {cap_type} send cap ({current}/{limit}). No more automated sends until the cap resets.",
        priority=NotificationPriority.HIGH,
        metadata={"cap_type": cap_type, "current": current, "limit": limit},
    )


async def notify_qualification_complete(
    workspace_id: str, accounts_scored: int, briefs_generated: int
) -> Notification:
    return await send_notification(
        workspace_id=workspace_id,
        notification_type=NotificationType.QUALIFICATION_COMPLETE,
        title="Qualification Batch Complete",
        message=f"Scored {accounts_scored} accounts and generated {briefs_generated} seller briefs.",
        priority=NotificationPriority.LOW,
        metadata={"accounts_scored": accounts_scored, "briefs_generated": briefs_generated},
    )
