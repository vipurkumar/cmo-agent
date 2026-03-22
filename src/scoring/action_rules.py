"""Deterministic next-best-action engine for OmniGTM.

Applies configurable threshold logic to decide: pursue_now, nurture,
disqualify, or human_review_required. No LLM calls — pure rules.
"""

from __future__ import annotations

from src.agent.state import (
    AccountScore,
    ActionRecommendation,
    ActionType,
    PainHypothesis,
    RankedContact,
)
from src.config.action_thresholds import ACTION_THRESHOLDS


def recommend_action(
    score: AccountScore,
    top_contact: RankedContact | None,
    pain_hypotheses: list[PainHypothesis],
    thresholds: dict | None = None,
) -> ActionRecommendation:
    """Decide the next-best-action for an account.

    Decision logic (evaluated in order):
    1. If disqualified by ICP scorer → disqualify
    2. If evidence conflicts or overall confidence < threshold → human_review
    3. If all pursue thresholds met → pursue_now
    4. If fit is decent but timing/pain weak → nurture
    5. If fit is weak → disqualify
    6. Default → human_review_required
    """
    t = thresholds or ACTION_THRESHOLDS

    pursue = t["pursue_now"]
    nurture = t["nurture"]
    disqualify = t["disqualify"]
    human_review = t["human_review_required"]

    top_pain_confidence = max(
        (ph.confidence_score for ph in pain_hypotheses), default=0.0
    )
    top_contact_relevance = top_contact.relevance_score if top_contact else 0

    threshold_details = {
        "overall_priority_threshold": pursue["overall_priority_min"],
        "overall_priority_actual": score.overall_priority_score,
        "contact_relevance_threshold": pursue["top_contact_relevance_min"],
        "contact_relevance_actual": top_contact_relevance,
        "pain_confidence_threshold": pursue["pain_confidence_min"],
        "pain_confidence_actual": round(top_pain_confidence, 2),
    }

    # 1. Already disqualified by ICP scorer
    if score.is_disqualified:
        return ActionRecommendation(
            action=ActionType.DISQUALIFY,
            explanation=score.disqualify_reason or "Disqualified by ICP scoring rules",
            confidence_score=0.95,
            threshold_details=threshold_details,
        )

    # 2. Low overall confidence → human review
    if score.confidence_score < human_review["confidence_min"]:
        return ActionRecommendation(
            action=ActionType.HUMAN_REVIEW_REQUIRED,
            explanation=(
                f"Overall confidence ({score.confidence_score:.2f}) is below "
                f"threshold ({human_review['confidence_min']}). "
                "Insufficient evidence for automated decision."
            ),
            best_first_contact=top_contact,
            confidence_score=score.confidence_score,
            threshold_details=threshold_details,
        )

    # 3. All pursue thresholds met → pursue_now
    meets_priority = score.overall_priority_score >= pursue["overall_priority_min"]
    meets_contact = top_contact_relevance >= pursue["top_contact_relevance_min"]
    meets_pain = top_pain_confidence >= pursue["pain_confidence_min"]

    if meets_priority and meets_contact and meets_pain:
        multi_thread = (
            top_contact is not None
            and len(pain_hypotheses) > 1
            and top_contact_relevance >= 70
        )
        return ActionRecommendation(
            action=ActionType.PURSUE_NOW,
            explanation=(
                f"Strong fit ({score.overall_priority_score}/100), "
                f"clear pain owner ({top_contact.name if top_contact else 'N/A'}, "
                f"relevance {top_contact_relevance}), "
                f"and confident pain hypothesis ({top_pain_confidence:.2f}). "
                "All thresholds exceeded."
            ),
            best_first_contact=top_contact,
            best_channel="email",
            multi_threading_recommended=multi_thread,
            confidence_score=min(score.confidence_score, top_pain_confidence),
            threshold_details=threshold_details,
        )

    # 4. Decent fit but weak timing/pain → nurture
    if score.icp_fit_score >= nurture["icp_fit_min"]:
        weak_timing = score.timing_score < nurture["timing_max"]
        weak_pain = top_pain_confidence < nurture["pain_confidence_max"]
        if weak_timing or weak_pain:
            reasons = []
            if weak_timing:
                reasons.append(f"timing is weak ({score.timing_score}/100)")
            if weak_pain:
                reasons.append(f"pain confidence is low ({top_pain_confidence:.2f})")
            return ActionRecommendation(
                action=ActionType.NURTURE,
                explanation=(
                    f"ICP fit is decent ({score.icp_fit_score}/100) "
                    f"but {' and '.join(reasons)}. "
                    "Recommend monitoring for stronger signals."
                ),
                best_first_contact=top_contact,
                confidence_score=score.confidence_score * 0.8,
                threshold_details=threshold_details,
            )

    # 5. Weak fit → disqualify
    if score.icp_fit_score < disqualify["icp_fit_max"]:
        return ActionRecommendation(
            action=ActionType.DISQUALIFY,
            explanation=(
                f"ICP fit score ({score.icp_fit_score}/100) is below "
                f"disqualify threshold ({disqualify['icp_fit_max']}). "
                "Account does not match target profile."
            ),
            confidence_score=score.confidence_score,
            threshold_details=threshold_details,
        )

    # 6. Default → human review
    return ActionRecommendation(
        action=ActionType.HUMAN_REVIEW_REQUIRED,
        explanation=(
            "Account does not clearly meet pursue or nurture criteria. "
            f"Priority: {score.overall_priority_score}/100, "
            f"contact relevance: {top_contact_relevance}, "
            f"pain confidence: {top_pain_confidence:.2f}. "
            "Recommend manual review."
        ),
        best_first_contact=top_contact,
        confidence_score=score.confidence_score * 0.7,
        threshold_details=threshold_details,
    )
