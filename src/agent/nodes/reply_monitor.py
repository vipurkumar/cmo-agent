"""reply_monitor node — checks for replies via n8n webhook.

If a reply is found, uses call_claude() with SYSTEM_REPLY_ANALYZER to
classify the intent. Returns a ReplyAnalysis or empty dict if no reply.
"""

from __future__ import annotations

import json

import httpx

from src.agent.state import OutboundState, ReplyAnalysis
from src.config import settings
from src.llm.budget import call_claude
from src.llm.prompts import SYSTEM_REPLY_ANALYZER
from src.logger import log


async def reply_monitor(state: OutboundState) -> dict:
    """Check for a reply to the last sent message and classify its intent."""
    thread_id = state["thread_id"]
    account = state["current_account"]
    if account is None:
        return {}

    workspace_id = account.workspace_id
    log.info("reply_monitor.start", thread_id=thread_id, workspace_id=workspace_id)

    contact = state.get("current_contact")
    campaign = state.get("campaign")

    if contact is None:
        log.warning(
            "reply_monitor.no_contact",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        return {}

    # Check for replies via n8n webhook
    params = {
        "workspace_id": workspace_id,
        "contact_email": contact.email,
        "campaign_id": campaign.id if campaign else "",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.N8N_WEBHOOK_BASE_URL}/check-reply",
            params=params,
            headers={"X-Workspace-Id": workspace_id},
        )

    if resp.status_code != 200:
        log.warning(
            "reply_monitor.webhook_error",
            thread_id=thread_id,
            workspace_id=workspace_id,
            status_code=resp.status_code,
        )
        return {}

    data = resp.json()
    reply_text = data.get("reply_text", "")

    if not reply_text:
        log.info(
            "reply_monitor.no_reply",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        return {}

    # Classify the reply intent using Claude (haiku for classification)
    user_prompt = (
        f"## Original Email Context\n"
        f"To: {contact.email}\n"
        f"Company: {account.company_name}\n\n"
        f"## Reply\n{reply_text}\n\n"
        "Classify this reply and respond with JSON."
    )

    raw = await call_claude(
        task="reply_analysis",
        system=SYSTEM_REPLY_ANALYZER,
        user=user_prompt,
        workspace_id=workspace_id,
        model=settings.CLAUDE_HAIKU_MODEL,
    )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning(
            "reply_monitor.json_parse_failed",
            thread_id=thread_id,
            workspace_id=workspace_id,
            raw=raw[:200],
        )
        parsed = {
            "intent": "neutral",
            "confidence": 0.0,
            "reasoning": "Failed to parse classification",
            "suggested_action": "pause_sequence",
        }

    analysis = ReplyAnalysis(
        intent=parsed.get("intent", "neutral"),
        confidence=parsed.get("confidence", 0.0),
        reasoning=parsed.get("reasoning", ""),
        suggested_action=parsed.get("suggested_action", ""),
    )

    log.info(
        "reply_monitor.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        intent=analysis.intent,
        confidence=analysis.confidence,
    )

    return {"reply_analysis": analysis}
