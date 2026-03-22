"""sender node — sends the approved email via n8n webhook.

Makes an HTTP call to N8N_WEBHOOK_BASE_URL/send-email and persists the
message record via the DB queries module.
"""

from __future__ import annotations

import httpx

from src.agent.state import Message, OutboundState
from src.config import settings
from src.db.queries import async_session_factory, save_message
from src.logger import log


async def sender(state: OutboundState) -> dict:
    """Send the approved email and record it in the database."""
    thread_id = state["thread_id"]
    account = state["current_account"]
    if account is None:
        return {"error": "No current_account set"}

    workspace_id = account.workspace_id
    log.info("sender.start", thread_id=thread_id, workspace_id=workspace_id)

    draft = state.get("draft_email")
    contact = state.get("current_contact")
    campaign = state.get("campaign")
    current_stage = state.get("current_stage", 1)

    if draft is None or contact is None:
        log.error(
            "sender.missing_data",
            thread_id=thread_id,
            workspace_id=workspace_id,
            has_draft=draft is not None,
            has_contact=contact is not None,
        )
        return {"error": "Missing draft or contact for sending"}

    # 1. Send email via n8n webhook
    payload = {
        "to": contact.email,
        "subject": draft.subject_line,
        "body": draft.body,
        "workspace_id": workspace_id,
        "campaign_id": campaign.id if campaign else "",
        "contact_id": contact.id,
        "stage": current_stage,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.N8N_WEBHOOK_BASE_URL}/send-email",
            json=payload,
            headers={"X-Workspace-Id": workspace_id},
        )

    if resp.status_code >= 400:
        log.error(
            "sender.webhook_error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            status_code=resp.status_code,
        )
        return {"error": f"Email send failed with status {resp.status_code}"}

    # 2. Persist the sent message in the database
    async with async_session_factory() as session, session.begin():
        db_message = await save_message(
            session=session,
            workspace_id=workspace_id,
            contact_id=contact.id,
            campaign_id=campaign.id if campaign else "",
            subject=draft.subject_line,
            body=draft.body,
            stage=str(current_stage),
        )

    # Build state Message model
    sent_msg = Message(
        id=db_message.id,
        workspace_id=workspace_id,
        contact_id=contact.id,
        campaign_id=campaign.id if campaign else "",
        subject=draft.subject_line,
        body=draft.body,
        stage=current_stage,
        status="sent",
    )

    existing = list(state.get("sent_messages", []))
    existing.append(sent_msg)

    log.info(
        "sender.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        contact_email=contact.email,
        stage=current_stage,
    )

    return {"sent_messages": existing}
