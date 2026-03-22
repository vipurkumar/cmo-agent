"""LangGraph StateGraph wiring — no business logic lives here.

All node functions are imported from src.agent.nodes.* and wired together
with conditional edges. Uses AsyncRedisSaver for checkpointing.
"""

from __future__ import annotations

from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph

from src.agent.nodes.account_selector import account_selector
from src.agent.nodes.approval_gate import approval_gate
from src.agent.nodes.enrichment_retry import enrichment_retry
from src.agent.nodes.memory_updater import memory_updater
from src.agent.nodes.notify_sales import notify_sales
from src.agent.nodes.personaliser import personaliser
from src.agent.nodes.reply_monitor import reply_monitor
from src.agent.nodes.researcher import researcher
from src.agent.nodes.router import router
from src.agent.nodes.sender import sender
from src.agent.nodes.unsubscribe_handler import unsubscribe_handler
from src.agent.state import OutboundState
from src.config import settings

# ---------------------------------------------------------------------------
# Conditional-edge routing functions
# ---------------------------------------------------------------------------


def _after_researcher(state: OutboundState) -> str:
    """Route after researcher: retry enrichment on failure, else personalise."""
    if state.get("error") and state.get("enrichment") is None:
        return "enrichment_retry"
    return "personaliser"


def _after_approval_gate(state: OutboundState) -> str:
    """Route after approval gate: send if approved, end if rejected."""
    if state.get("approval_status") == "approved":
        return "sender"
    return END


def _after_router(state: OutboundState) -> str:
    """Route based on reply analysis or sequence continuation."""
    reply = state.get("reply_analysis")
    if reply is not None:
        if reply.intent == "positive":
            return "notify_sales"
        if reply.intent == "unsubscribe":
            return "unsubscribe_handler"

    # Check if there are more stages in the sequence
    current_stage = state.get("current_stage", 1)
    max_stages = state.get("max_stages", 3)
    if current_stage < max_stages and state.get("should_continue", False):
        return "personaliser"

    return "memory_updater"


def _after_memory_updater(state: OutboundState) -> str:
    """Route after memory update: next account or end."""
    accounts = state.get("accounts", [])
    current = state.get("current_account")
    if current is not None and accounts:
        current_idx = next(
            (i for i, a in enumerate(accounts) if a.id == current.id),
            -1,
        )
        if current_idx < len(accounts) - 1:
            return "account_selector"
    return END


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    """Build the outbound agent StateGraph with all nodes and edges."""
    graph = StateGraph(OutboundState)

    # --- Add nodes ---
    graph.add_node("account_selector", account_selector)
    graph.add_node("researcher", researcher)
    graph.add_node("personaliser", personaliser)
    graph.add_node("approval_gate", approval_gate)
    graph.add_node("sender", sender)
    graph.add_node("reply_monitor", reply_monitor)
    graph.add_node("router", router)
    graph.add_node("memory_updater", memory_updater)
    graph.add_node("notify_sales", notify_sales)
    graph.add_node("enrichment_retry", enrichment_retry)
    graph.add_node("unsubscribe_handler", unsubscribe_handler)

    # --- Add edges ---
    graph.add_edge(START, "account_selector")
    graph.add_edge("account_selector", "researcher")
    graph.add_conditional_edges("researcher", _after_researcher)
    graph.add_edge("personaliser", "approval_gate")
    graph.add_conditional_edges("approval_gate", _after_approval_gate)
    graph.add_edge("sender", "reply_monitor")
    graph.add_edge("reply_monitor", "router")
    graph.add_conditional_edges("router", _after_router)
    graph.add_conditional_edges("memory_updater", _after_memory_updater)
    graph.add_edge("enrichment_retry", "researcher")
    graph.add_edge("notify_sales", "memory_updater")
    graph.add_edge("unsubscribe_handler", "memory_updater")

    return graph


async def create_graph():
    """Return a compiled graph with AsyncRedisSaver checkpointing."""
    async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
        graph = build_graph()
        return graph.compile(checkpointer=checkpointer)
