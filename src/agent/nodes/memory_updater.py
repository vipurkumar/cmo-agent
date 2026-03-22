"""memory_updater node — stores campaign learnings and resets account state.

Persists enrichment data and outcome signals to pgvector via
campaign_memory.store_embedding(), then resets current_account state
so the graph can proceed to the next account.
"""

from __future__ import annotations

from src.agent.state import OutboundState
from src.db.campaign_memory import store_embedding
from src.db.queries import async_session_factory
from src.llm.embeddings import embed_text
from src.logger import log


async def memory_updater(state: OutboundState) -> dict:
    """Store campaign learnings in pgvector and reset state for next account."""
    thread_id = state["thread_id"]
    account = state["current_account"]
    workspace_id = account.workspace_id if account else state.get("workspace_id", "")
    log.info("memory_updater.start", thread_id=thread_id, workspace_id=workspace_id)

    campaign = state.get("campaign")
    enrichment = state.get("enrichment")
    reply = state.get("reply_analysis")
    draft = state.get("draft_email")

    # Build a memory content string summarising this account interaction
    memory_parts = []
    if account:
        memory_parts.append(f"Account: {account.company_name} ({account.domain or 'no domain'})")
    if enrichment:
        memory_parts.append(f"Summary: {enrichment.company_summary}")
        if enrichment.pain_points:
            memory_parts.append(f"Pain points: {', '.join(enrichment.pain_points)}")
    if draft:
        memory_parts.append(f"Email subject: {draft.subject_line}")
    if reply:
        memory_parts.append(f"Reply intent: {reply.intent} (confidence: {reply.confidence})")
        memory_parts.append(f"Suggested action: {reply.suggested_action}")

    content = "\n".join(memory_parts) if memory_parts else "No data to store"

    # Store in pgvector with a real embedding of the memory content
    if campaign and memory_parts:
        try:
            embedding_vector = await embed_text(content, input_type="document")

            async with async_session_factory() as session, session.begin():
                await store_embedding(
                    session=session,
                    workspace_id=workspace_id,
                    campaign_id=campaign.id,
                    content=content,
                    embedding_vector=embedding_vector,
                )

            log.info(
                "memory_updater.stored",
                thread_id=thread_id,
                workspace_id=workspace_id,
                content_length=len(content),
            )
        except Exception as exc:
            log.error(
                "memory_updater.store_error",
                thread_id=thread_id,
                workspace_id=workspace_id,
                error=str(exc),
            )

    log.info("memory_updater.complete", thread_id=thread_id, workspace_id=workspace_id)

    # Reset current-account state keys so account_selector can pick the next one
    return {
        "current_account": state.get("current_account"),  # keep for _after_memory_updater routing
        "current_contact": None,
        "enrichment": None,
        "draft_email": None,
        "approval_status": None,
        "reply_analysis": None,
        "error": None,
        "should_continue": True,
    }
