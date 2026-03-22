"""Notification API endpoints for workspace event notifications."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.api.deps import WorkspaceDep
from src.notifications.notifier import (
    get_notifications,
    get_unread_count,
    mark_as_read,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    workspace_id: WorkspaceDep,
    unread_only: bool = False,
    limit: int = 50,
):
    """Get notifications for the workspace."""
    notifications = await get_notifications(
        workspace_id=workspace_id,
        unread_only=unread_only,
        limit=limit,
    )
    return {
        "notifications": [n.model_dump(mode="json") for n in notifications],
        "unread_count": await get_unread_count(workspace_id),
        "total": len(notifications),
    }


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    workspace_id: WorkspaceDep,
):
    """Mark a notification as read."""
    success = await mark_as_read(workspace_id, notification_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "read"}


@router.get("/unread-count")
async def unread_notification_count(workspace_id: WorkspaceDep):
    """Get the count of unread notifications."""
    return {"unread_count": await get_unread_count(workspace_id)}
