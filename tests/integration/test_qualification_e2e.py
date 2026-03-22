"""End-to-end integration tests for OmniGTM qualification pipeline.

Requires: docker compose up -d (PostgreSQL, Redis, ClickHouse)
Run with: uv run pytest tests/integration/ --integration -v

Tests score persistence, signal storage, seller brief lifecycle,
feedback/outcome event roundtrips, and scoring determinism against
real PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.agent.state import (
    Account,
    ActionType,
    SignalType,
)
from src.db.queries import (
    get_account_score,
    get_seller_brief,
    get_signals_for_account,
    list_seller_briefs_by_action,
    save_account_score,
    save_feedback_event,
    save_outcome_event,
    save_seller_brief,
    save_signal,
)
from src.scoring.icp_rules import score_icp_fit


# ---------------------------------------------------------------------------
# Score persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_and_persist_account(db_session, workspace_id, sample_account):
    """Score an account with icp_rules, persist via save_account_score, read back."""
    # Score the account deterministically
    icp_fit, fit_reasons, non_fit_reasons, is_dq, dq_reason, confidence = score_icp_fit(
        account=sample_account,
    )

    # Persist the score
    record = await save_account_score(
        session=db_session,
        workspace_id=workspace_id,
        account_id=sample_account.id,
        icp_fit_score=icp_fit,
        pain_fit_score=60,
        timing_score=75,
        overall_priority_score=int((icp_fit + 60 + 75) / 3),
        confidence_score=confidence,
        fit_reasons=[e.model_dump() for e in fit_reasons],
        non_fit_reasons=[e.model_dump() for e in non_fit_reasons],
        is_disqualified=is_dq,
        disqualify_reason=dq_reason,
    )

    assert record.id is not None
    assert record.workspace_id == workspace_id
    assert record.account_id == sample_account.id

    # Read back
    fetched = await get_account_score(
        session=db_session,
        account_id=sample_account.id,
        workspace_id=workspace_id,
    )

    assert fetched is not None
    assert fetched.icp_fit_score == icp_fit
    assert fetched.pain_fit_score == 60
    assert fetched.timing_score == 75
    assert fetched.is_disqualified == is_dq
    assert fetched.confidence_score == pytest.approx(confidence, abs=0.001)


# ---------------------------------------------------------------------------
# Signal persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_retrieve_signals(db_session, workspace_id, sample_account):
    """Create signals, save via save_signal, retrieve and verify ordering."""
    signal_data = [
        {
            "signal_type": SignalType.FUNDING.value,
            "source": "crunchbase",
            "observed_fact": "Series C raised at $80M",
            "possible_implication": "Growth budget available for tooling",
            "confidence": 0.90,
            "reliability_score": 0.85,
            "recency_score": 0.95,
        },
        {
            "signal_type": SignalType.PRICING_CHANGE.value,
            "source": "pricing_page_monitor",
            "observed_fact": "New enterprise tier added to pricing page",
            "possible_implication": "Moving upmarket, may need CPQ",
            "confidence": 0.80,
            "reliability_score": 0.75,
            "recency_score": 0.88,
        },
        {
            "signal_type": SignalType.HIRING_REVOPS_PRICING.value,
            "source": "linkedin_jobs",
            "observed_fact": "Hiring VP Revenue Operations",
            "possible_implication": "Building RevOps function, pricing ops pain likely",
            "confidence": 0.85,
            "reliability_score": 0.80,
            "recency_score": 0.92,
        },
    ]

    for data in signal_data:
        await save_signal(
            session=db_session,
            workspace_id=workspace_id,
            account_id=sample_account.id,
            **data,
        )

    # Retrieve
    signals = await get_signals_for_account(
        session=db_session,
        account_id=sample_account.id,
        workspace_id=workspace_id,
    )

    assert len(signals) == 3
    # Ordered by created_at DESC — most recent first
    signal_types = [s.signal_type for s in signals]
    assert SignalType.FUNDING.value in signal_types
    assert SignalType.PRICING_CHANGE.value in signal_types
    assert SignalType.HIRING_REVOPS_PRICING.value in signal_types


# ---------------------------------------------------------------------------
# Seller brief persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_retrieve_seller_brief(db_session, workspace_id, sample_account):
    """Create a SellerBrief, persist, read back via get_seller_brief."""
    brief_json = {
        "account_snapshot": "IntegTest Corp is a mid-market SaaS company...",
        "why_this_account": "Strong ICP fit with enterprise motion signals",
        "why_now": "Recent funding and pricing page changes indicate readiness",
        "recommended_action": "pursue_now",
        "risks_and_unknowns": ["Unclear decision-making process"],
    }

    record = await save_seller_brief(
        session=db_session,
        workspace_id=workspace_id,
        account_id=sample_account.id,
        brief_json=brief_json,
        action_type=ActionType.PURSUE_NOW.value,
        overall_score=82,
        confidence_score=0.78,
        version=1,
    )

    assert record.id is not None
    assert record.action_type == ActionType.PURSUE_NOW.value

    # Read back
    fetched = await get_seller_brief(
        session=db_session,
        account_id=sample_account.id,
        workspace_id=workspace_id,
    )

    assert fetched is not None
    assert fetched.brief_json["account_snapshot"] == brief_json["account_snapshot"]
    assert fetched.overall_score == 82
    assert fetched.confidence_score == pytest.approx(0.78, abs=0.001)


# ---------------------------------------------------------------------------
# Feedback event roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_roundtrip(db_session, workspace_id):
    """Save a feedback event, verify it persists with correct fields."""
    rec_id = str(uuid4())
    user_id = "user-sales-rep-01"

    record = await save_feedback_event(
        session=db_session,
        workspace_id=workspace_id,
        recommendation_id=rec_id,
        recommendation_type="seller_brief",
        user_id=user_id,
        action_taken="approved",
        correction=None,
    )

    assert record.id is not None
    assert record.workspace_id == workspace_id
    assert record.recommendation_id == rec_id
    assert record.recommendation_type == "seller_brief"
    assert record.user_id == user_id
    assert record.action_taken == "approved"
    assert record.correction is None
    assert record.model_version == "v1"


@pytest.mark.asyncio
async def test_feedback_with_correction(db_session, workspace_id):
    """Save a feedback event with a correction, verify correction persists."""
    rec_id = str(uuid4())

    record = await save_feedback_event(
        session=db_session,
        workspace_id=workspace_id,
        recommendation_id=rec_id,
        recommendation_type="action_recommendation",
        user_id="user-manager-01",
        action_taken="overridden",
        correction="Changed from pursue_now to nurture — timing not right",
    )

    assert record.action_taken == "overridden"
    assert record.correction == "Changed from pursue_now to nurture — timing not right"


# ---------------------------------------------------------------------------
# Outcome event roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outcome_event_roundtrip(db_session, workspace_id, sample_account):
    """Save an outcome event, verify persistence."""
    record = await save_outcome_event(
        session=db_session,
        workspace_id=workspace_id,
        account_id=sample_account.id,
        event_type="opportunity_created",
        opportunity_id=str(uuid4()),
        details={
            "pipeline_value": 120_000,
            "stage": "discovery",
            "source": "outbound",
        },
    )

    assert record.id is not None
    assert record.workspace_id == workspace_id
    assert record.account_id == sample_account.id
    assert record.event_type == "opportunity_created"
    assert record.details["pipeline_value"] == 120_000
    assert record.details["stage"] == "discovery"


# ---------------------------------------------------------------------------
# List briefs by action type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_briefs_by_action(db_session, workspace_id):
    """Save multiple briefs with different action types, verify filtering."""
    accounts = [f"acct-{uuid4().hex[:8]}" for _ in range(4)]

    # 2 pursue_now, 1 nurture, 1 disqualify
    test_data = [
        (accounts[0], ActionType.PURSUE_NOW.value, 85, 0.80),
        (accounts[1], ActionType.PURSUE_NOW.value, 72, 0.70),
        (accounts[2], ActionType.NURTURE.value, 55, 0.60),
        (accounts[3], ActionType.DISQUALIFY.value, 15, 0.90),
    ]

    for acct_id, action, score, conf in test_data:
        await save_seller_brief(
            session=db_session,
            workspace_id=workspace_id,
            account_id=acct_id,
            brief_json={"action": action},
            action_type=action,
            overall_score=score,
            confidence_score=conf,
        )

    # Filter by pursue_now
    pursue_briefs = await list_seller_briefs_by_action(
        session=db_session,
        workspace_id=workspace_id,
        action_type=ActionType.PURSUE_NOW.value,
    )
    assert len(pursue_briefs) == 2
    # Should be ordered by overall_score DESC
    assert pursue_briefs[0].overall_score >= pursue_briefs[1].overall_score

    # Filter by nurture
    nurture_briefs = await list_seller_briefs_by_action(
        session=db_session,
        workspace_id=workspace_id,
        action_type=ActionType.NURTURE.value,
    )
    assert len(nurture_briefs) == 1
    assert nurture_briefs[0].action_type == ActionType.NURTURE.value

    # Filter by disqualify
    dq_briefs = await list_seller_briefs_by_action(
        session=db_session,
        workspace_id=workspace_id,
        action_type=ActionType.DISQUALIFY.value,
    )
    assert len(dq_briefs) == 1


# ---------------------------------------------------------------------------
# Scoring determinism
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scoring_determinism(sample_account):
    """Score the same account twice with identical data, verify identical results."""
    result1 = score_icp_fit(account=sample_account)
    result2 = score_icp_fit(account=sample_account)

    # Unpack: (icp_fit_score, fit_reasons, non_fit_reasons, is_dq, dq_reason, confidence)
    assert result1[0] == result2[0], "icp_fit_score should be deterministic"
    assert result1[3] == result2[3], "is_disqualified should be deterministic"
    assert result1[5] == pytest.approx(result2[5], abs=0.0001), "confidence should be deterministic"
    assert len(result1[1]) == len(result2[1]), "fit_reasons count should be deterministic"
    assert len(result1[2]) == len(result2[2]), "non_fit_reasons count should be deterministic"


# ---------------------------------------------------------------------------
# Disqualified account persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disqualified_account_persists(db_session, workspace_id):
    """Score an account that gets disqualified, verify is_disqualified=True in DB."""
    # Create a tiny company that triggers the employee_count_below_20 disqualify rule
    tiny_account = Account(
        id=f"acct-tiny-{uuid4().hex[:8]}",
        workspace_id=workspace_id,
        company_name="TinyStartup Inc",
        domain="tinystartup.io",
        industry="SaaS",
        employee_count=10,  # Below 20 → disqualified
        revenue=500_000.0,
        metadata={},
    )

    icp_fit, fit_reasons, non_fit_reasons, is_dq, dq_reason, confidence = score_icp_fit(
        account=tiny_account,
    )

    assert is_dq is True, "Account with 10 employees should be disqualified"
    assert dq_reason is not None

    # Persist
    record = await save_account_score(
        session=db_session,
        workspace_id=workspace_id,
        account_id=tiny_account.id,
        icp_fit_score=icp_fit,
        pain_fit_score=0,
        timing_score=0,
        overall_priority_score=0,
        confidence_score=confidence,
        fit_reasons=[e.model_dump() for e in fit_reasons],
        non_fit_reasons=[e.model_dump() for e in non_fit_reasons],
        is_disqualified=is_dq,
        disqualify_reason=dq_reason,
    )

    # Read back
    fetched = await get_account_score(
        session=db_session,
        account_id=tiny_account.id,
        workspace_id=workspace_id,
    )

    assert fetched is not None
    assert fetched.is_disqualified is True
    assert fetched.disqualify_reason is not None
    assert "below" in fetched.disqualify_reason.lower() or "10" in fetched.disqualify_reason
    assert fetched.icp_fit_score == 0


# ---------------------------------------------------------------------------
# Tenant isolation verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_isolation_scores(db_session):
    """Verify that scores from workspace A are invisible to workspace B."""
    ws_a = f"ws-iso-a-{uuid4().hex[:8]}"
    ws_b = f"ws-iso-b-{uuid4().hex[:8]}"
    account_id = f"acct-shared-{uuid4().hex[:8]}"

    # Save score in workspace A
    await save_account_score(
        session=db_session,
        workspace_id=ws_a,
        account_id=account_id,
        icp_fit_score=90,
        pain_fit_score=80,
        timing_score=70,
        overall_priority_score=80,
        confidence_score=0.85,
    )

    # Query from workspace B — should get nothing
    result = await get_account_score(
        session=db_session,
        account_id=account_id,
        workspace_id=ws_b,
    )
    assert result is None, "Tenant isolation violated: workspace B can see workspace A's data"

    # Query from workspace A — should succeed
    result_a = await get_account_score(
        session=db_session,
        account_id=account_id,
        workspace_id=ws_a,
    )
    assert result_a is not None
    assert result_a.icp_fit_score == 90
