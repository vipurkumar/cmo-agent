"""Webhook subscription management API."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from src.api.deps import SessionDep, WorkspaceDep
from src.db.queries import Base, async_session_factory
from src.logger import log
from sqlalchemy import Column, DateTime, String, Text, Integer, Boolean, func
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from uuid import uuid4


router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks-management"])


# ORM model (inline since it's specific to this feature)
class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    events = Column(ARRAY(String), nullable=False, default=[])
    secret: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CreateWebhookRequest(BaseModel):
    url: str = Field(..., min_length=10)
    events: list[str] = Field(
        default_factory=lambda: ["brief_ready", "automation_paused", "qualification_complete"],
        description="Event types to subscribe to",
    )


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    secret: str
    is_active: bool


VALID_EVENTS = {
    "brief_ready",
    "automation_paused",
    "automation_resumed",
    "high_error_rate",
    "send_cap_reached",
    "kill_switch_triggered",
    "qualification_complete",
    "evaluation_complete",
}


@router.post("", status_code=201)
async def create_webhook_route(
    body: CreateWebhookRequest,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Register a webhook URL to receive events."""
    # Validate events
    invalid = set(body.events) - VALID_EVENTS
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event types: {invalid}. Valid: {sorted(VALID_EVENTS)}",
        )

    webhook_secret = secrets.token_urlsafe(32)

    sub = WebhookSubscription(
        workspace_id=workspace_id,
        url=body.url,
        events=body.events,
        secret=webhook_secret,
    )
    session.add(sub)
    await session.flush()

    log.info("api.webhook_created", workspace_id=workspace_id, url=body.url)

    return {
        "id": sub.id,
        "url": sub.url,
        "events": body.events,
        "secret": webhook_secret,
        "is_active": True,
        "message": "Use this secret to verify webhook signatures (X-Webhook-Signature header)",
    }


@router.get("")
async def list_webhooks_route(
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """List all webhook subscriptions."""
    result = await session.execute(
        select(WebhookSubscription)
        .where(WebhookSubscription.workspace_id == workspace_id)
        .order_by(WebhookSubscription.created_at.desc())
    )
    subs = result.scalars().all()
    return {
        "webhooks": [
            {
                "id": s.id,
                "url": s.url,
                "events": s.events or [],
                "is_active": s.is_active,
                "created_at": str(s.created_at) if s.created_at else None,
            }
            for s in subs
        ],
    }


@router.delete("/{webhook_id}")
async def delete_webhook_route(
    webhook_id: str,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Deactivate a webhook subscription."""
    result = await session.execute(
        update(WebhookSubscription)
        .where(WebhookSubscription.id == webhook_id)
        .where(WebhookSubscription.workspace_id == workspace_id)
        .values(is_active=False)
    )
    await session.flush()
    if (result.rowcount or 0) == 0:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "deactivated"}


@router.post("/{webhook_id}/test")
async def test_webhook_route(
    webhook_id: str,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Send a test event to a webhook."""
    result = await session.execute(
        select(WebhookSubscription)
        .where(WebhookSubscription.id == webhook_id)
        .where(WebhookSubscription.workspace_id == workspace_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook not found")

    from src.webhooks.dispatcher import dispatch_webhook

    delivery = await dispatch_webhook(
        url=sub.url,
        secret=sub.secret,
        event_type="test",
        payload={"message": "This is a test webhook from CMO Agent"},
        workspace_id=workspace_id,
    )
    return {"delivery": delivery}
