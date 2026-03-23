"""OmniGTM Qualification Graph — intelligence pipeline wiring.

Produces a SellerBrief for each account by running:
  data_ingester → entity_resolver → [per account loop]:
    icp_scorer → signal_detector → contact_ranker →
    pain_inferrer → value_prop_matcher → action_recommender →
    brief_builder → brief_reviewer → crm_writer → zoho_writer →
    task_creator → auto_outbound_gate

Uses AsyncRedisSaver for checkpointing.
No business logic lives here — only graph wiring.
"""

from __future__ import annotations

from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph

from src.agent.nodes.action_recommender import action_recommender
from src.agent.nodes.auto_outbound_gate import auto_outbound_gate
from src.agent.nodes.brief_builder import brief_builder
from src.agent.nodes.brief_reviewer import brief_reviewer
from src.agent.nodes.contact_ranker import contact_ranker
from src.agent.nodes.crm_writer import crm_writer
from src.agent.nodes.data_ingester import data_ingester
from src.agent.nodes.draft_email_generator import draft_email_generator
from src.agent.nodes.entity_resolver import entity_resolver
from src.agent.nodes.icp_scorer import icp_scorer
from src.agent.nodes.pain_inferrer import pain_inferrer
from src.agent.nodes.signal_detector import signal_detector
from src.agent.nodes.task_creator import task_creator
from src.agent.nodes.value_prop_matcher import value_prop_matcher
from src.agent.nodes.zoho_writer import zoho_writer
from src.agent.state import QualificationState
from src.config import settings

# ---------------------------------------------------------------------------
# Account iteration routing
# ---------------------------------------------------------------------------


def _after_auto_outbound(state: QualificationState) -> str:
    """After auto-outbound gate, route to draft email generator if triggered."""
    auto_triggered = state.get("auto_outbound_triggered", False)
    recommendation = state.get("action_recommendation")
    is_pursue_now = recommendation and recommendation.action.value == "pursue_now"

    # Generate draft emails when auto-outbound triggered or action is pursue_now
    # (in draft-only mode, auto_outbound_triggered is set without enqueuing)
    if auto_triggered or is_pursue_now:
        return "draft_email_generator"

    return _after_draft_email(state)


def _after_draft_email(state: QualificationState) -> str:
    """After draft email generation, advance to next account or end."""
    accounts = state.get("accounts", [])
    current = state.get("current_account")

    if current is not None and accounts:
        current_idx = next(
            (i for i, a in enumerate(accounts) if a.id == current.id),
            -1,
        )
        if current_idx < len(accounts) - 1:
            return "select_next_account"

    return END


def _after_icp_scorer(state: QualificationState) -> str:
    """Skip rest of pipeline for disqualified accounts."""
    score = state.get("account_score")
    if score is not None and score.is_disqualified:
        return "action_recommender"
    return "signal_detector"


def _after_brief_reviewer(state: QualificationState) -> str:
    """Route after brief review — proceed to CRM writeback."""
    approval = state.get("approval_status")
    if approval == "pending_review":
        # Graph will interrupt here and wait for webhook callback
        return END
    # auto_approved or approved → continue to writeback
    return "crm_writer"


# ---------------------------------------------------------------------------
# Account selector (lightweight — picks next account from list)
# ---------------------------------------------------------------------------


async def select_next_account(state: QualificationState) -> dict:
    """Advance to the next account in the batch."""
    accounts = state.get("accounts", [])
    current = state.get("current_account")

    if not accounts:
        return {"should_continue": False}

    if current is None:
        next_account = accounts[0]
    else:
        current_idx = next(
            (i for i, a in enumerate(accounts) if a.id == current.id),
            -1,
        )
        if current_idx < len(accounts) - 1:
            next_account = accounts[current_idx + 1]
        else:
            return {"should_continue": False}

    return {
        "current_account": next_account,
        "signals": [],
        "pain_hypotheses": [],
        "value_props": [],
        "ranked_contacts": [],
        "buying_committee": None,
        "account_score": None,
        "seller_brief": None,
        "action_recommendation": None,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_qualification_graph() -> StateGraph:
    """Build the OmniGTM qualification pipeline graph.

    Pipeline:
      START → data_ingester → entity_resolver → select_next_account
        → icp_scorer → [disqualified? → action_recommender]
        → signal_detector → contact_ranker → pain_inferrer
        → value_prop_matcher → action_recommender → brief_builder
        → brief_reviewer → [pending_review? → END (interrupt)]
        → crm_writer → zoho_writer → task_creator
        → [more accounts? → select_next_account : END]
    """
    graph = StateGraph(QualificationState)

    # --- Add nodes ---
    # Intelligence pipeline
    graph.add_node("data_ingester", data_ingester)
    graph.add_node("entity_resolver", entity_resolver)
    graph.add_node("select_next_account", select_next_account)
    graph.add_node("icp_scorer", icp_scorer)
    graph.add_node("signal_detector", signal_detector)
    graph.add_node("contact_ranker", contact_ranker)
    graph.add_node("pain_inferrer", pain_inferrer)
    graph.add_node("value_prop_matcher", value_prop_matcher)
    graph.add_node("action_recommender", action_recommender)
    graph.add_node("brief_builder", brief_builder)

    # Phase 3: Review, writeback, tasks
    graph.add_node("brief_reviewer", brief_reviewer)
    graph.add_node("crm_writer", crm_writer)
    graph.add_node("zoho_writer", zoho_writer)
    graph.add_node("task_creator", task_creator)

    # Phase 4: Narrow automation
    graph.add_node("auto_outbound_gate", auto_outbound_gate)

    # Phase 4b: Draft email generation (no-send mode)
    graph.add_node("draft_email_generator", draft_email_generator)

    # --- Add edges ---
    # Ingestion phase
    graph.add_edge(START, "data_ingester")
    graph.add_edge("data_ingester", "entity_resolver")
    graph.add_edge("entity_resolver", "select_next_account")

    # Per-account intelligence loop
    graph.add_edge("select_next_account", "icp_scorer")
    graph.add_conditional_edges("icp_scorer", _after_icp_scorer)
    graph.add_edge("signal_detector", "contact_ranker")
    graph.add_edge("contact_ranker", "pain_inferrer")
    graph.add_edge("pain_inferrer", "value_prop_matcher")
    graph.add_edge("value_prop_matcher", "action_recommender")
    graph.add_edge("action_recommender", "brief_builder")

    # Phase 3: Review → CRM writeback → Tasks
    graph.add_edge("brief_builder", "brief_reviewer")
    graph.add_conditional_edges("brief_reviewer", _after_brief_reviewer)
    graph.add_edge("crm_writer", "zoho_writer")
    graph.add_edge("zoho_writer", "task_creator")

    # Phase 4: Auto-outbound gate → Draft emails → Next account
    graph.add_edge("task_creator", "auto_outbound_gate")
    graph.add_conditional_edges("auto_outbound_gate", _after_auto_outbound)
    graph.add_conditional_edges("draft_email_generator", _after_draft_email)

    return graph


async def create_qualification_graph():
    """Return a compiled qualification graph with AsyncRedisSaver checkpointing."""
    async with AsyncRedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
        graph = build_qualification_graph()
        return graph.compile(checkpointer=checkpointer)
