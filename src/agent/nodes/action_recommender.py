"""action_recommender node — deterministic next-best-action via pure rules.

No LLM calls. Delegates to src.scoring.action_rules.recommend_action()
which applies configurable threshold logic.
"""

from __future__ import annotations

from src.agent.state import ActionRecommendation, ActionType, QualificationState
from src.logger import log
from src.scoring.action_rules import recommend_action


async def action_recommender(state: QualificationState) -> dict:
    """Determine the next-best-action for the current account using rules."""
    thread_id = state["thread_id"]
    account = state.get("current_account")
    if account is None:
        return {"error": "No current_account set"}

    workspace_id = account.workspace_id
    log.info("action_recommender.start", thread_id=thread_id, workspace_id=workspace_id)

    account_score = state.get("account_score")
    ranked_contacts = state.get("ranked_contacts", [])
    pain_hypotheses = state.get("pain_hypotheses", [])

    if account_score is None:
        log.warning(
            "action_recommender.no_score",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        recommendation = ActionRecommendation(
            action=ActionType.HUMAN_REVIEW_REQUIRED,
            explanation="No account score available — cannot make automated decision.",
            confidence_score=0.0,
        )
        return {"action_recommendation": recommendation}

    top_contact = ranked_contacts[0] if ranked_contacts else None

    recommendation = recommend_action(
        score=account_score,
        top_contact=top_contact,
        pain_hypotheses=pain_hypotheses,
    )

    log.info(
        "action_recommender.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        action=recommendation.action.value,
        confidence=recommendation.confidence_score,
    )
    return {"action_recommendation": recommendation}
