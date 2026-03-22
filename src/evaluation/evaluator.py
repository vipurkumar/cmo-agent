"""OmniGTM evaluator — runs evaluation against a test set of accounts.

Scores a batch of accounts, compares against ground truth labels,
and produces an evaluation report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from src.agent.state import (
    Account,
    AccountScore,
    ActionType,
    PainHypothesis,
    RankedContact,
)
from src.evaluation.metrics import (
    acceptance_rate,
    action_override_rate,
    confidence_calibration,
    contact_ranking_precision,
    precision_at_k,
    scoring_distribution,
)
from src.logger import log
from src.scoring.action_rules import recommend_action
from src.scoring.icp_rules import score_icp_fit


@dataclass
class EvaluationReport:
    """Results from an evaluation run against ground truth test accounts."""

    run_id: str
    timestamp: datetime
    scoring_version: str
    account_count: int
    metrics: dict[str, Any]
    per_account_results: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report for API responses."""
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "scoring_version": self.scoring_version,
            "account_count": self.account_count,
            "metrics": self.metrics,
            "per_account_results": self.per_account_results,
        }

    def summary(self) -> str:
        """Human-readable summary of the evaluation."""
        lines = [
            f"Evaluation Report: {self.run_id}",
            f"Timestamp: {self.timestamp.isoformat()}",
            f"Scoring Version: {self.scoring_version}",
            f"Accounts Evaluated: {self.account_count}",
            "",
            "--- Metrics ---",
        ]

        for metric_name, value in self.metrics.items():
            if isinstance(value, float):
                lines.append(f"  {metric_name}: {value:.4f}")
            elif isinstance(value, dict):
                lines.append(f"  {metric_name}:")
                for sub_key, sub_val in value.items():
                    if isinstance(sub_val, dict):
                        lines.append(f"    {sub_key}: {sub_val}")
                    else:
                        lines.append(f"    {sub_key}: {sub_val}")
            else:
                lines.append(f"  {metric_name}: {value}")

        # Action distribution
        action_counts: dict[str, int] = {}
        correct_count = 0
        for result in self.per_account_results:
            predicted = result.get("predicted_action", "unknown")
            action_counts[predicted] = action_counts.get(predicted, 0) + 1
            if result.get("action_correct"):
                correct_count += 1

        lines.append("")
        lines.append("--- Action Distribution ---")
        for action, count in sorted(action_counts.items()):
            lines.append(f"  {action}: {count}")

        lines.append("")
        lines.append(f"Action Accuracy: {correct_count}/{self.account_count}")

        return "\n".join(lines)


def _build_account(test_account: dict[str, Any], workspace_id: str) -> Account:
    """Construct an Account from test data dict."""
    data = test_account["account_data"]
    return Account(
        id=data.get("id", str(uuid4())),
        workspace_id=workspace_id,
        company_name=data["company_name"],
        domain=data.get("domain"),
        industry=data.get("industry"),
        employee_count=data.get("employee_count"),
        revenue=data.get("revenue"),
        metadata=data.get("metadata", {}),
    )


def _build_pain_hypotheses(test_account: dict[str, Any]) -> list[PainHypothesis]:
    """Build synthetic PainHypothesis list from test account data."""
    pain_data = test_account.get("account_data", {}).get("metadata", {}).get("pain_hypotheses", [])
    hypotheses = []
    for ph in pain_data:
        hypotheses.append(PainHypothesis(
            pain_type=ph.get("pain_type", "pricing_complexity"),
            score=ph.get("score", 50),
            confidence_score=ph.get("confidence_score", 0.5),
        ))
    return hypotheses


def _build_top_contact(test_account: dict[str, Any]) -> RankedContact | None:
    """Build a synthetic RankedContact from test account data."""
    contact_data = test_account.get("account_data", {}).get("metadata", {}).get("top_contact")
    if not contact_data:
        return None
    return RankedContact(
        contact_id=contact_data.get("contact_id", str(uuid4())),
        name=contact_data.get("name", "Unknown"),
        title=contact_data.get("title", "Unknown"),
        normalized_function=contact_data.get("normalized_function", "unknown"),
        normalized_seniority=contact_data.get("normalized_seniority", "unknown"),
        relevance_score=contact_data.get("relevance_score", 50),
        likely_role=contact_data.get("likely_role", "unknown"),
        reason_for_relevance=contact_data.get("reason_for_relevance", ""),
        confidence_score=contact_data.get("confidence_score", 0.5),
    )


def _normalize_action(action_str: str) -> str:
    """Normalize action strings for comparison."""
    return action_str.lower().replace(" ", "_").replace("-", "_")


async def run_evaluation(
    test_accounts: list[dict[str, Any]],
    workspace_id: str,
    scoring_version: str = "v1",
) -> EvaluationReport:
    """Score a batch of test accounts and compare against ground truth.

    Parameters
    ----------
    test_accounts:
        List of dicts with keys:
        - account_data: dict matching Account model fields
        - ground_truth_action: "pursue_now" | "nurture" | "disqualify" | "human_review"
        - ground_truth_contact: expected first contact title (optional)
        - notes: why this label is correct
    workspace_id:
        Tenant workspace ID for scoring context.
    scoring_version:
        Version label for the scoring run.

    Returns
    -------
    EvaluationReport with all computed metrics.
    """
    run_id = str(uuid4())
    log.info(
        "evaluation.run_start",
        run_id=run_id,
        workspace_id=workspace_id,
        account_count=len(test_accounts),
        scoring_version=scoring_version,
    )

    per_account_results: list[dict[str, Any]] = []
    scored_accounts: list[dict[str, Any]] = []
    all_scores: list[dict[str, Any]] = []
    calibration_predictions: list[tuple[float, bool]] = []

    # Ground truth sets for precision@k
    ground_truth_pursue = set()
    ground_truth_good = set()  # pursue_now + nurture

    for test_acct in test_accounts:
        gt_action = _normalize_action(test_acct.get("ground_truth_action", ""))
        acct_id = test_acct["account_data"].get("id", str(uuid4()))
        test_acct["account_data"]["id"] = acct_id

        if gt_action == "pursue_now":
            ground_truth_pursue.add(acct_id)
            ground_truth_good.add(acct_id)
        elif gt_action == "nurture":
            ground_truth_good.add(acct_id)

    for test_acct in test_accounts:
        account = _build_account(test_acct, workspace_id)
        pain_hypotheses = _build_pain_hypotheses(test_acct)
        top_contact = _build_top_contact(test_acct)

        gt_action = _normalize_action(test_acct.get("ground_truth_action", ""))
        gt_contact = test_acct.get("ground_truth_contact", "")

        # Score ICP fit
        icp_fit_score, fit_reasons, non_fit_reasons, is_dq, dq_reason, confidence = (
            score_icp_fit(account)
        )

        # Build AccountScore for action recommendation
        # Use pain/timing from metadata if provided, otherwise derive from ICP
        meta = test_acct.get("account_data", {}).get("metadata", {})
        pain_fit_score = meta.get("pain_fit_score", 50)
        timing_score = meta.get("timing_score", 50)

        # Overall priority is weighted combination
        overall = int(
            icp_fit_score * 0.35
            + pain_fit_score * 0.30
            + timing_score * 0.35
        )

        account_score = AccountScore(
            account_id=account.id,
            workspace_id=workspace_id,
            icp_fit_score=icp_fit_score,
            pain_fit_score=pain_fit_score,
            timing_score=timing_score,
            overall_priority_score=overall,
            fit_reasons=fit_reasons,
            non_fit_reasons=non_fit_reasons,
            confidence_score=confidence,
            is_disqualified=is_dq,
            disqualify_reason=dq_reason,
            scoring_version=scoring_version,
        )

        # Get action recommendation
        action_rec = recommend_action(
            score=account_score,
            top_contact=top_contact,
            pain_hypotheses=pain_hypotheses,
        )

        predicted_action = _normalize_action(action_rec.action.value)
        action_correct = predicted_action == gt_action

        # Contact ranking precision
        contact_precision = 0.0
        ranked_contacts_data = meta.get("ranked_contacts", [])
        if gt_contact and ranked_contacts_data:
            contact_precision = contact_ranking_precision(
                ranked_contacts_data, gt_contact, k=3
            )
        elif gt_contact and top_contact:
            # Use the single top contact as a one-element ranking
            contact_precision = contact_ranking_precision(
                [{"title": top_contact.title, "normalized_function": top_contact.normalized_function, "relevance_score": top_contact.relevance_score}],
                gt_contact,
                k=3,
            )

        # Calibration data
        calibration_predictions.append((action_rec.confidence_score, action_correct))

        score_dict = {
            "icp_fit_score": icp_fit_score,
            "pain_fit_score": pain_fit_score,
            "timing_score": timing_score,
            "overall_priority_score": overall,
            "confidence_score": confidence,
        }
        all_scores.append(score_dict)

        scored_accounts.append({
            "account_id": account.id,
            "overall_priority_score": overall,
        })

        per_account_results.append({
            "account_id": account.id,
            "company_name": account.company_name,
            "ground_truth_action": gt_action,
            "predicted_action": predicted_action,
            "action_correct": action_correct,
            "icp_fit_score": icp_fit_score,
            "pain_fit_score": pain_fit_score,
            "timing_score": timing_score,
            "overall_priority_score": overall,
            "confidence_score": round(confidence, 4),
            "is_disqualified": is_dq,
            "action_explanation": action_rec.explanation,
            "contact_precision": contact_precision,
            "ground_truth_contact": gt_contact,
        })

    # Compute aggregate metrics
    total = len(per_account_results)
    correct = sum(1 for r in per_account_results if r["action_correct"])
    action_accuracy = correct / total if total > 0 else 0.0

    # Precision at various k values
    p_at_5 = precision_at_k(scored_accounts, ground_truth_pursue, k=5)
    p_at_10 = precision_at_k(scored_accounts, ground_truth_pursue, k=10)
    p_at_15 = precision_at_k(scored_accounts, ground_truth_good, k=15)

    # Average contact ranking precision
    contact_precisions = [r["contact_precision"] for r in per_account_results if r["ground_truth_contact"]]
    avg_contact_precision = (
        sum(contact_precisions) / len(contact_precisions)
        if contact_precisions
        else 0.0
    )

    # Confidence calibration
    calibration = confidence_calibration(calibration_predictions)

    # Scoring distribution
    score_dist = scoring_distribution(all_scores)

    # Per-action accuracy
    action_groups: dict[str, list[bool]] = {}
    for r in per_account_results:
        gt = r["ground_truth_action"]
        action_groups.setdefault(gt, []).append(r["action_correct"])

    per_action_accuracy = {}
    for action, outcomes in action_groups.items():
        per_action_accuracy[action] = {
            "accuracy": round(sum(outcomes) / len(outcomes), 4) if outcomes else 0.0,
            "count": len(outcomes),
        }

    metrics = {
        "action_accuracy": round(action_accuracy, 4),
        "precision_at_5_pursue": round(p_at_5, 4),
        "precision_at_10_pursue": round(p_at_10, 4),
        "precision_at_15_good": round(p_at_15, 4),
        "avg_contact_ranking_precision": round(avg_contact_precision, 4),
        "confidence_calibration": calibration,
        "scoring_distribution": score_dist,
        "per_action_accuracy": per_action_accuracy,
    }

    report = EvaluationReport(
        run_id=run_id,
        timestamp=datetime.now(UTC),
        scoring_version=scoring_version,
        account_count=total,
        metrics=metrics,
        per_account_results=per_account_results,
    )

    log.info(
        "evaluation.run_complete",
        run_id=run_id,
        workspace_id=workspace_id,
        action_accuracy=action_accuracy,
        account_count=total,
    )

    return report


def compare_versions(
    report_a: EvaluationReport,
    report_b: EvaluationReport,
) -> dict[str, Any]:
    """Compare two evaluation runs and show deltas for each metric.

    Parameters
    ----------
    report_a:
        Baseline evaluation report.
    report_b:
        New evaluation report to compare against baseline.

    Returns
    -------
    Dict with metric deltas and improvement indicators.
    """
    result: dict[str, Any] = {
        "baseline": {
            "run_id": report_a.run_id,
            "scoring_version": report_a.scoring_version,
            "timestamp": report_a.timestamp.isoformat(),
        },
        "comparison": {
            "run_id": report_b.run_id,
            "scoring_version": report_b.scoring_version,
            "timestamp": report_b.timestamp.isoformat(),
        },
        "deltas": {},
    }

    # Compare top-level numeric metrics
    scalar_metrics = [
        "action_accuracy",
        "precision_at_5_pursue",
        "precision_at_10_pursue",
        "precision_at_15_good",
        "avg_contact_ranking_precision",
    ]

    for metric in scalar_metrics:
        val_a = report_a.metrics.get(metric, 0.0)
        val_b = report_b.metrics.get(metric, 0.0)
        delta = val_b - val_a
        result["deltas"][metric] = {
            "baseline": round(val_a, 4),
            "comparison": round(val_b, 4),
            "delta": round(delta, 4),
            "improved": delta > 0,
        }

    # Compare per-action accuracy
    per_action_a = report_a.metrics.get("per_action_accuracy", {})
    per_action_b = report_b.metrics.get("per_action_accuracy", {})
    all_actions = set(per_action_a.keys()) | set(per_action_b.keys())

    action_deltas: dict[str, Any] = {}
    for action in all_actions:
        acc_a = per_action_a.get(action, {}).get("accuracy", 0.0)
        acc_b = per_action_b.get(action, {}).get("accuracy", 0.0)
        delta = acc_b - acc_a
        action_deltas[action] = {
            "baseline": round(acc_a, 4),
            "comparison": round(acc_b, 4),
            "delta": round(delta, 4),
            "improved": delta > 0,
        }
    result["deltas"]["per_action_accuracy"] = action_deltas

    # Overall verdict
    improving_count = sum(
        1 for m in scalar_metrics if result["deltas"][m]["improved"]
    )
    result["overall_improved"] = improving_count > len(scalar_metrics) / 2

    return result
