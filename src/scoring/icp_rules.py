"""Deterministic ICP scoring engine for OmniGTM.

Produces icp_fit_score (0–100) from account attributes and ICP criteria.
No LLM calls — pure weighted rules. Pain fit scoring is handled separately
by the LLM-based pain_inferrer node.
"""

from __future__ import annotations

from src.agent.state import Account, Evidence, EvidenceType
from src.config.icp import DEFAULT_ICP, ICP_WEIGHTS


def _score_industry(account: Account, icp: dict) -> tuple[int, Evidence | None]:
    """Score industry match: 100 if in list, 0 if not."""
    industries = icp.get("industries", [])
    if not industries or not account.industry:
        return 50, None  # unknown = neutral

    industry_lower = account.industry.lower()
    for target in industries:
        if target.lower() in industry_lower or industry_lower in target.lower():
            return 100, Evidence(
                statement=f"Industry '{account.industry}' matches ICP target",
                evidence_type=EvidenceType.FACT,
                source="icp_scorer",
                confidence=0.95,
            )
    return 10, Evidence(
        statement=f"Industry '{account.industry}' is not in ICP target list",
        evidence_type=EvidenceType.FACT,
        source="icp_scorer",
        confidence=0.90,
    )


def _score_company_size(account: Account, icp: dict) -> tuple[int, Evidence | None]:
    """Score company size within min/max range."""
    size_range = icp.get("company_size", {})
    min_size = size_range.get("min", 0)
    max_size = size_range.get("max", float("inf"))

    if account.employee_count is None:
        return 50, None

    count = account.employee_count
    if min_size <= count <= max_size:
        # Score higher for sweet spot (middle of range)
        midpoint = (min_size + max_size) / 2
        distance = abs(count - midpoint) / (max_size - min_size) if max_size > min_size else 0
        score = int(100 - (distance * 40))  # 60–100 range within ICP
        return score, Evidence(
            statement=f"{count} employees is within ICP range ({min_size}–{max_size})",
            evidence_type=EvidenceType.FACT,
            source="icp_scorer",
            confidence=0.95,
        )

    if count < min_size:
        # Partial credit for being close
        ratio = count / min_size if min_size > 0 else 0
        score = int(max(0, ratio * 40))
        return score, Evidence(
            statement=f"{count} employees is below ICP minimum ({min_size})",
            evidence_type=EvidenceType.FACT,
            source="icp_scorer",
            confidence=0.90,
        )

    # Above max
    ratio = max_size / count if count > 0 else 0
    score = int(max(0, ratio * 40))
    return score, Evidence(
        statement=f"{count} employees is above ICP maximum ({max_size})",
        evidence_type=EvidenceType.FACT,
        source="icp_scorer",
        confidence=0.90,
    )


def _score_revenue(account: Account, icp: dict) -> tuple[int, Evidence | None]:
    """Score revenue within min/max range."""
    rev_range = icp.get("revenue_range", {})
    min_rev = rev_range.get("min", 0)
    max_rev = rev_range.get("max", float("inf"))

    if account.revenue is None:
        return 50, None

    revenue = account.revenue
    if min_rev <= revenue <= max_rev:
        midpoint = (min_rev + max_rev) / 2
        distance = abs(revenue - midpoint) / (max_rev - min_rev) if max_rev > min_rev else 0
        score = int(100 - (distance * 40))
        return score, Evidence(
            statement=f"Revenue ${revenue:,.0f} is within ICP range",
            evidence_type=EvidenceType.FACT,
            source="icp_scorer",
            confidence=0.85,
        )

    return 15, Evidence(
        statement=f"Revenue ${revenue:,.0f} is outside ICP range (${min_rev:,.0f}–${max_rev:,.0f})",
        evidence_type=EvidenceType.FACT,
        source="icp_scorer",
        confidence=0.85,
    )


def _score_geography(account: Account, icp: dict) -> tuple[int, Evidence | None]:
    """Score geography match."""
    geos = icp.get("geographies", [])
    if not geos:
        return 50, None

    # Check account metadata for geography
    geo = account.metadata.get("geography") or account.metadata.get("country")
    if not geo:
        return 50, None

    geo_upper = geo.upper()
    if geo_upper in [g.upper() for g in geos]:
        return 100, Evidence(
            statement=f"Geography '{geo}' matches ICP targets",
            evidence_type=EvidenceType.FACT,
            source="icp_scorer",
            confidence=0.95,
        )
    return 20, Evidence(
        statement=f"Geography '{geo}' is not in ICP target list",
        evidence_type=EvidenceType.FACT,
        source="icp_scorer",
        confidence=0.85,
    )


def _score_metadata_signals(account: Account, icp: dict) -> tuple[int, list[Evidence]]:
    """Score based on positive/negative signals in account metadata."""
    positive_signals = icp.get("positive_signals", [])
    negative_signals = icp.get("negative_signals", [])
    signals = account.metadata.get("signals", [])
    if not signals:
        return 50, []

    score = 50
    evidence: list[Evidence] = []

    for signal in signals:
        signal_lower = signal.lower() if isinstance(signal, str) else ""
        if any(pos.lower() in signal_lower or signal_lower in pos.lower() for pos in positive_signals):
            score = min(100, score + 15)
            evidence.append(Evidence(
                statement=f"Positive signal detected: {signal}",
                evidence_type=EvidenceType.FACT,
                source="icp_scorer",
                confidence=0.80,
            ))
        if any(neg.lower() in signal_lower or signal_lower in neg.lower() for neg in negative_signals):
            score = max(0, score - 25)
            evidence.append(Evidence(
                statement=f"Negative signal detected: {signal}",
                evidence_type=EvidenceType.FACT,
                source="icp_scorer",
                confidence=0.80,
            ))

    return score, evidence


def _check_disqualify(account: Account, icp: dict) -> tuple[bool, str | None]:
    """Check explicit disqualify rules."""
    rules = icp.get("disqualify_rules", [])
    for rule in rules:
        if rule == "employee_count_below_20" and account.employee_count is not None:
            if account.employee_count < 20:
                return True, f"Company has {account.employee_count} employees (below 20 minimum)"
        if rule == "pre_revenue" and account.revenue is not None:
            if account.revenue <= 0:
                return True, "Company is pre-revenue"
        if rule == "existing_customer":
            if account.metadata.get("is_customer"):
                return True, "Company is already a customer"
    return False, None


def score_icp_fit(
    account: Account,
    icp: dict | None = None,
    weights: dict[str, float] | None = None,
) -> tuple[int, list[Evidence], list[Evidence], bool, str | None, float]:
    """Score an account against ICP criteria.

    Returns
    -------
    tuple of:
        icp_fit_score (0–100),
        fit_reasons (list[Evidence]),
        non_fit_reasons (list[Evidence]),
        is_disqualified (bool),
        disqualify_reason (str | None),
        confidence (float)
    """
    icp = icp or DEFAULT_ICP
    weights = weights or ICP_WEIGHTS

    # Check disqualify first
    is_dq, dq_reason = _check_disqualify(account, icp)
    if is_dq:
        return 0, [], [Evidence(
            statement=dq_reason or "Disqualified",
            evidence_type=EvidenceType.FACT,
            source="icp_scorer",
            confidence=0.95,
        )], True, dq_reason, 0.95

    # Score each dimension
    fit_reasons: list[Evidence] = []
    non_fit_reasons: list[Evidence] = []
    weighted_total = 0.0
    total_weight = 0.0
    confidence_sum = 0.0
    dimension_count = 0

    scorers: list[tuple[str, tuple[int, Evidence | None]]] = [
        ("industry", _score_industry(account, icp)),
        ("company_size", _score_company_size(account, icp)),
        ("revenue", _score_revenue(account, icp)),
        ("geography", _score_geography(account, icp)),
    ]

    for dimension, (dim_score, evidence) in scorers:
        weight = weights.get(dimension, 0.0)
        weighted_total += dim_score * weight
        total_weight += weight
        if evidence:
            dimension_count += 1
            confidence_sum += evidence.confidence
            if dim_score >= 60:
                fit_reasons.append(evidence)
            else:
                non_fit_reasons.append(evidence)

    # Signal-based scoring
    signal_weight = (
        weights.get("monetization_complexity", 0.0)
        + weights.get("growth_stage", 0.0)
        + weights.get("enterprise_sales_motion", 0.0)
    )
    signal_score, signal_evidence = _score_metadata_signals(account, icp)
    weighted_total += signal_score * signal_weight
    total_weight += signal_weight
    for ev in signal_evidence:
        if "Positive" in ev.statement:
            fit_reasons.append(ev)
        else:
            non_fit_reasons.append(ev)
        confidence_sum += ev.confidence
        dimension_count += 1

    # Account for unmeasured dimensions with neutral score
    remaining_weight = 1.0 - total_weight
    if remaining_weight > 0:
        weighted_total += 50 * remaining_weight

    icp_fit_score = int(min(100, max(0, round(weighted_total))))
    confidence = confidence_sum / dimension_count if dimension_count > 0 else 0.3

    return icp_fit_score, fit_reasons, non_fit_reasons, False, None, confidence
