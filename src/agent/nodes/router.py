"""router node — decides the next action based on reply analysis and stage.

Sets should_continue and current_stage to drive the conditional edges
defined in graph.py.
"""

from __future__ import annotations

from src.agent.state import OutboundState
from src.logger import log


async def router(state: OutboundState) -> dict:
    """Route to the next step based on reply analysis and sequence progress."""
    thread_id = state["thread_id"]
    account = state["current_account"]
    workspace_id = account.workspace_id if account else state.get("workspace_id", "")
    log.info("router.start", thread_id=thread_id, workspace_id=workspace_id)

    reply = state.get("reply_analysis")
    current_stage = state.get("current_stage", 1)
    max_stages = state.get("max_stages", 3)

    # If there's a reply, route based on intent
    if reply is not None:
        if reply.intent == "positive":
            log.info(
                "router.positive_reply",
                thread_id=thread_id,
                workspace_id=workspace_id,
            )
            return {"should_continue": False}

        if reply.intent == "unsubscribe":
            log.info(
                "router.unsubscribe",
                thread_id=thread_id,
                workspace_id=workspace_id,
            )
            return {"should_continue": False}

        if reply.intent == "negative":
            log.info(
                "router.negative_reply",
                thread_id=thread_id,
                workspace_id=workspace_id,
            )
            return {"should_continue": False}

    # No reply or neutral — check if we can advance to next stage
    if current_stage < max_stages:
        next_stage = current_stage + 1
        log.info(
            "router.next_stage",
            thread_id=thread_id,
            workspace_id=workspace_id,
            next_stage=next_stage,
        )
        return {
            "should_continue": True,
            "current_stage": next_stage,
            "reply_analysis": None,
        }

    # All stages exhausted
    log.info(
        "router.sequence_complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        final_stage=current_stage,
    )
    return {"should_continue": False, "current_stage": current_stage}
