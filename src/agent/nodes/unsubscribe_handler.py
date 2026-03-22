"""unsubscribe_handler node — processes unsubscribe requests.

Updates the contact status in the database and stops the sequence
for this account. Unsubscribe compliance is a legal requirement and
MUST be handled immediately.
"""

from __future__ import annotations

from src.agent.state import OutboundState
from src.db.queries import async_session_factory, update_message_status
from src.logger import log


async def unsubscribe_handler(state: OutboundState) -> dict:
    """Process an unsubscribe request — update DB and stop the sequence."""
    thread_id = state["thread_id"]
    account = state["current_account"]
    workspace_id = account.workspace_id if account else state.get("workspace_id", "")
    log.info("unsubscribe_handler.start", thread_id=thread_id, workspace_id=workspace_id)

    contact = state.get("current_contact")
    sent_messages = state.get("sent_messages", [])

    # Mark all sent messages for this contact as unsubscribed
    if contact and sent_messages:
        try:
            async with async_session_factory() as session, session.begin():
                for msg in sent_messages:
                    if msg.contact_id == contact.id:
                        await update_message_status(
                            session=session,
                            message_id=msg.id,
                            workspace_id=workspace_id,
                            status="unsubscribed",
                        )
            log.info(
                "unsubscribe_handler.messages_updated",
                thread_id=thread_id,
                workspace_id=workspace_id,
                contact_email=contact.email,
            )
        except Exception as exc:
            log.error(
                "unsubscribe_handler.db_error",
                thread_id=thread_id,
                workspace_id=workspace_id,
                error=str(exc),
            )

    log.info(
        "unsubscribe_handler.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
    )

    return {"should_continue": False}
