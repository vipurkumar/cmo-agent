"""OmniGTM evaluation metrics — measures system quality and calibration.

Computes component-level and business metrics from scoring data,
feedback events, and outcome events.
"""

from __future__ import annotations

import statistics
from typing import Any

from src.logger import log


def precision_at_k(
    scored_accounts: list[dict[str, Any]],
    ground_truth_good: set[str],
    k: int,
) -> float:
    """Top-k precision: what fraction of top-k scored accounts are actually good.

    Parameters
    ----------
    scored_accounts:
        List of dicts with at least ``account_id`` and ``overall_priority_score``,
        sorted descending by score (or will be sorted here).
    ground_truth_good:
        Set of account_id values that are known-good (e.g. pursue_now).
    k:
        Number of top accounts to evaluate.

    Returns
    -------
    float in [0.0, 1.0]. Returns 0.0 if k <= 0 or list is empty.
    """
    if k <= 0 or not scored_accounts:
        return 0.0

    sorted_accounts = sorted(
        scored_accounts,
        key=lambda a: a.get("overall_priority_score", 0),
        reverse=True,
    )
    top_k = sorted_accounts[:k]
    hits = sum(
        1 for a in top_k if a.get("account_id") in ground_truth_good
    )
    return hits / k


def acceptance_rate(feedback_events: list[dict[str, Any]]) -> float:
    """Fraction of recommendations accepted (thumbs_up / total).

    Parameters
    ----------
    feedback_events:
        List of dicts with ``action_taken`` field. Accepted actions are
        "thumbs_up", "accepted", or "approved".

    Returns
    -------
    float in [0.0, 1.0]. Returns 0.0 if no events.
    """
    if not feedback_events:
        return 0.0

    accepted_actions = {"thumbs_up", "accepted", "approved"}
    accepted = sum(
        1
        for e in feedback_events
        if e.get("action_taken", "").lower() in accepted_actions
    )
    return accepted / len(feedback_events)


def contact_ranking_precision(
    ranked_contacts: list[dict[str, Any]],
    ground_truth_first_contact: str,
    k: int = 3,
) -> float:
    """Was the correct first contact in the top k?

    Parameters
    ----------
    ranked_contacts:
        List of dicts with ``title`` or ``normalized_function``, sorted by
        relevance_score descending.
    ground_truth_first_contact:
        Expected title or function string for the best first contact.
    k:
        How many top contacts to check.

    Returns
    -------
    1.0 if the ground truth contact is found in the top k, 0.0 otherwise.
    """
    if not ranked_contacts or not ground_truth_first_contact:
        return 0.0

    sorted_contacts = sorted(
        ranked_contacts,
        key=lambda c: c.get("relevance_score", 0),
        reverse=True,
    )
    top_k = sorted_contacts[:k]
    gt_lower = ground_truth_first_contact.lower()

    for contact in top_k:
        title = (contact.get("title") or "").lower()
        function = (contact.get("normalized_function") or "").lower()
        if gt_lower in title or gt_lower in function or title in gt_lower or function in gt_lower:
            return 1.0

    return 0.0


def confidence_calibration(
    predictions: list[tuple[float, bool]],
) -> dict[str, dict[str, Any]]:
    """Bin predictions by confidence, compute actual accuracy per bin.

    Parameters
    ----------
    predictions:
        List of (predicted_confidence, was_correct) tuples.

    Returns
    -------
    Dict mapping bin labels to {predicted_confidence, actual_accuracy, count}.
    """
    bins: dict[str, list[tuple[float, bool]]] = {
        "0.0-0.2": [],
        "0.2-0.4": [],
        "0.4-0.6": [],
        "0.6-0.8": [],
        "0.8-1.0": [],
    }

    for confidence, correct in predictions:
        confidence = max(0.0, min(1.0, confidence))
        if confidence < 0.2:
            bins["0.0-0.2"].append((confidence, correct))
        elif confidence < 0.4:
            bins["0.2-0.4"].append((confidence, correct))
        elif confidence < 0.6:
            bins["0.4-0.6"].append((confidence, correct))
        elif confidence < 0.8:
            bins["0.6-0.8"].append((confidence, correct))
        else:
            bins["0.8-1.0"].append((confidence, correct))

    result: dict[str, dict[str, Any]] = {}
    for label, items in bins.items():
        if not items:
            result[label] = {
                "predicted_confidence": 0.0,
                "actual_accuracy": 0.0,
                "count": 0,
            }
        else:
            avg_confidence = sum(c for c, _ in items) / len(items)
            accuracy = sum(1 for _, correct in items if correct) / len(items)
            result[label] = {
                "predicted_confidence": round(avg_confidence, 4),
                "actual_accuracy": round(accuracy, 4),
                "count": len(items),
            }

    return result


def action_override_rate(
    recommendations: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
) -> float:
    """How often did users override the recommended action.

    Parameters
    ----------
    recommendations:
        List of dicts with ``id`` and ``action`` fields.
    feedback:
        List of dicts with ``recommendation_id``, ``action_taken``, and
        optionally ``correction``.

    Returns
    -------
    float in [0.0, 1.0]. Returns 0.0 if no matching feedback found.
    """
    if not recommendations or not feedback:
        return 0.0

    rec_map = {r["id"]: r.get("action", "") for r in recommendations}
    matched = 0
    overridden = 0

    for fb in feedback:
        rec_id = fb.get("recommendation_id")
        if rec_id not in rec_map:
            continue
        matched += 1
        # Override detected if correction is present or action_taken differs
        # from the recommendation
        if fb.get("correction"):
            overridden += 1
        elif fb.get("action_taken", "").lower() not in {
            "accepted",
            "approved",
            "thumbs_up",
            rec_map[rec_id].lower(),
        }:
            overridden += 1

    return overridden / matched if matched > 0 else 0.0


def scoring_distribution(scores: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Distribution stats: mean, median, p25, p75, std for each score dimension.

    Parameters
    ----------
    scores:
        List of dicts with score dimensions: ``icp_fit_score``,
        ``pain_fit_score``, ``timing_score``, ``overall_priority_score``,
        ``confidence_score``.

    Returns
    -------
    Dict mapping dimension name to {mean, median, p25, p75, std}.
    """
    dimensions = [
        "icp_fit_score",
        "pain_fit_score",
        "timing_score",
        "overall_priority_score",
        "confidence_score",
    ]
    result: dict[str, dict[str, float]] = {}

    for dim in dimensions:
        values = [s[dim] for s in scores if dim in s and s[dim] is not None]
        if not values:
            result[dim] = {"mean": 0.0, "median": 0.0, "p25": 0.0, "p75": 0.0, "std": 0.0}
            continue

        sorted_values = sorted(values)
        n = len(sorted_values)

        mean_val = statistics.mean(sorted_values)
        median_val = statistics.median(sorted_values)
        std_val = statistics.stdev(sorted_values) if n >= 2 else 0.0

        # Percentiles using nearest-rank method
        p25_idx = max(0, int(n * 0.25) - 1)
        p75_idx = max(0, int(n * 0.75) - 1)
        p25_val = sorted_values[p25_idx]
        p75_val = sorted_values[p75_idx]

        result[dim] = {
            "mean": round(mean_val, 2),
            "median": round(median_val, 2),
            "p25": round(p25_val, 2),
            "p75": round(p75_val, 2),
            "std": round(std_val, 2),
        }

    return result


def signal_false_positive_rate(
    signals: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
) -> float:
    """Fraction of signals marked irrelevant by reps.

    Parameters
    ----------
    signals:
        List of signal dicts with ``id`` field.
    feedback:
        List of feedback dicts with ``recommendation_id`` and ``action_taken``
        fields. Signals are considered false positives when action_taken is
        "irrelevant", "false_positive", or "rejected".

    Returns
    -------
    float in [0.0, 1.0]. Returns 0.0 if no signal feedback found.
    """
    if not signals or not feedback:
        return 0.0

    signal_ids = {s["id"] for s in signals if "id" in s}
    false_positive_actions = {"irrelevant", "false_positive", "rejected"}

    matched = 0
    false_positives = 0

    for fb in feedback:
        rec_id = fb.get("recommendation_id")
        if rec_id not in signal_ids:
            continue
        matched += 1
        if fb.get("action_taken", "").lower() in false_positive_actions:
            false_positives += 1

    return false_positives / matched if matched > 0 else 0.0


def brief_usefulness_score(feedback: list[dict[str, Any]]) -> float:
    """Average rating from rep feedback on brief quality.

    Parameters
    ----------
    feedback:
        List of feedback dicts. Looks for ``rating`` (numeric 1-5) or
        derives a score from ``action_taken``:
        - "very_useful" / "thumbs_up" -> 5
        - "useful" / "accepted" -> 4
        - "neutral" -> 3
        - "not_useful" / "rejected" -> 2
        - "misleading" / "false_positive" -> 1

    Returns
    -------
    float in [1.0, 5.0]. Returns 0.0 if no feedback.
    """
    if not feedback:
        return 0.0

    action_to_score = {
        "very_useful": 5.0,
        "thumbs_up": 5.0,
        "useful": 4.0,
        "accepted": 4.0,
        "approved": 4.0,
        "neutral": 3.0,
        "not_useful": 2.0,
        "rejected": 2.0,
        "misleading": 1.0,
        "false_positive": 1.0,
    }

    ratings: list[float] = []
    for fb in feedback:
        if "rating" in fb and fb["rating"] is not None:
            ratings.append(float(fb["rating"]))
        else:
            action = fb.get("action_taken", "").lower()
            if action in action_to_score:
                ratings.append(action_to_score[action])

    if not ratings:
        return 0.0

    return round(statistics.mean(ratings), 2)
