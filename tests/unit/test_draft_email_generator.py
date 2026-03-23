"""Tests for the draft_email_generator node."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.state import (
    Account,
    AccountScore,
    ActionRecommendation,
    ActionType,
    BuyingRole,
    Contact,
    DraftEmail,
    Evidence,
    EvidenceType,
    PainHypothesis,
    PainType,
    QualificationState,
    RankedContact,
    SellerBrief,
    ValuePropRecommendation,
)


@pytest.fixture()
def qual_state_pursue_now() -> QualificationState:
    """A qualification state with a pursue_now account, contacts, and value props."""
    return {
        "thread_id": "test-thread",
        "workspace_id": "ws-test-001",
        "current_account": Account(
            id="acct-001",
            workspace_id="ws-test-001",
            company_name="NovaPay",
            domain="novapay.io",
            industry="FinTech",
            employee_count=450,
        ),
        "action_recommendation": ActionRecommendation(
            action=ActionType.PURSUE_NOW,
            explanation="High ICP fit + strong timing signals",
            confidence_score=0.82,
        ),
        "seller_brief": SellerBrief(
            id="brief-001",
            account_id="acct-001",
            workspace_id="ws-test-001",
            account_snapshot="NovaPay is a FinTech company...",
            why_this_account="Strong ICP fit...",
            why_now="Series C + RevOps hire...",
            likely_pain_points=[],
            recommended_contacts=[],
            persona_angles=[],
            risks_and_unknowns=[],
            recommended_action=ActionRecommendation(
                action=ActionType.PURSUE_NOW,
                explanation="Pursue",
            ),
            generated_at=datetime.now(timezone.utc),
        ),
        "ranked_contacts": [
            RankedContact(
                contact_id="ct-001",
                name="Sarah Chen",
                title="VP Revenue Operations",
                normalized_function="revenue_operations",
                normalized_seniority="vp",
                relevance_score=92,
                likely_role=BuyingRole.PAIN_OWNER,
                reason_for_relevance="Owns quote-to-cash",
            ),
            RankedContact(
                contact_id="ct-002",
                name="James Park",
                title="CFO",
                normalized_function="finance",
                normalized_seniority="c_suite",
                relevance_score=78,
                likely_role=BuyingRole.ECONOMIC_BUYER,
                reason_for_relevance="Budget authority",
            ),
        ],
        "contacts": [
            Contact(
                id="ct-001",
                workspace_id="ws-test-001",
                account_id="acct-001",
                email="sarah@novapay.io",
                first_name="Sarah",
                last_name="Chen",
                role="VP Revenue Operations",
            ),
            Contact(
                id="ct-002",
                workspace_id="ws-test-001",
                account_id="acct-001",
                email="james@novapay.io",
                first_name="James",
                last_name="Park",
                role="CFO",
            ),
        ],
        "value_props": [
            ValuePropRecommendation(
                contact_id="ct-001",
                top_problem="Manual quoting breaks down with usage-based pricing",
                relevant_capability="Automated usage-based quote generation",
                expected_business_outcome="60% faster quote turnaround",
                one_line_hook="We help FinTechs automate usage-based quoting",
                short_value_prop="Auto-generate quotes from metering data",
                likely_objection="Too early for CPQ",
                suggested_response="Best time to start",
            ),
        ],
    }


@pytest.mark.asyncio
async def test_draft_email_generator_creates_drafts(mock_settings, qual_state_pursue_now):
    """Should generate draft emails for top ranked contacts."""
    email_response = json.dumps({
        "subject": "Quick question about NovaPay's pricing ops",
        "body": "Hi Sarah, I noticed NovaPay recently shifted to usage-based pricing...",
    })

    with patch("src.agent.nodes.draft_email_generator.call_claude", new_callable=AsyncMock) as mock_claude, \
         patch("src.agent.nodes.draft_email_generator.settings", mock_settings):

        mock_claude.return_value = email_response

        from src.agent.nodes.draft_email_generator import draft_email_generator

        result = await draft_email_generator(qual_state_pursue_now)

        assert "draft_emails" in result
        drafts = result["draft_emails"]
        assert len(drafts) == 2  # Top 2 contacts with emails

        # Verify first draft
        assert drafts[0].contact_name == "Sarah Chen"
        assert drafts[0].contact_email == "sarah@novapay.io"
        assert "pricing" in drafts[0].subject_line.lower() or drafts[0].subject_line != ""
        assert drafts[0].body != ""

        # Verify call_claude was called twice (once per contact)
        assert mock_claude.call_count == 2


@pytest.mark.asyncio
async def test_draft_email_generator_skips_non_pursue_now(mock_settings):
    """Should return empty drafts for nurture/disqualify accounts."""
    state: QualificationState = {
        "thread_id": "test-thread",
        "workspace_id": "ws-test-001",
        "current_account": Account(
            id="acct-001",
            workspace_id="ws-test-001",
            company_name="SmallCo",
            domain="smallco.com",
        ),
        "action_recommendation": ActionRecommendation(
            action=ActionType.NURTURE,
            explanation="Low urgency",
        ),
    }

    with patch("src.agent.nodes.draft_email_generator.settings", mock_settings):
        from src.agent.nodes.draft_email_generator import draft_email_generator

        result = await draft_email_generator(state)

        assert result["draft_emails"] == []


@pytest.mark.asyncio
async def test_draft_email_generator_no_contacts(mock_settings):
    """Should return empty drafts when no ranked contacts available."""
    state: QualificationState = {
        "thread_id": "test-thread",
        "workspace_id": "ws-test-001",
        "current_account": Account(
            id="acct-001",
            workspace_id="ws-test-001",
            company_name="NoCo",
            domain="noco.com",
        ),
        "action_recommendation": ActionRecommendation(
            action=ActionType.PURSUE_NOW,
            explanation="High fit",
        ),
        "ranked_contacts": [],
        "contacts": [],
    }

    with patch("src.agent.nodes.draft_email_generator.settings", mock_settings):
        from src.agent.nodes.draft_email_generator import draft_email_generator

        result = await draft_email_generator(state)

        assert result["draft_emails"] == []


@pytest.mark.asyncio
async def test_draft_email_generator_handles_claude_failure(mock_settings, qual_state_pursue_now):
    """Should gracefully handle when Claude API fails for one contact."""
    call_count = 0

    async def mock_call_claude_side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Claude API error")
        return json.dumps({
            "subject": "Following up",
            "body": "Hi James, quick question...",
        })

    with patch("src.agent.nodes.draft_email_generator.call_claude", new_callable=AsyncMock) as mock_claude, \
         patch("src.agent.nodes.draft_email_generator.settings", mock_settings):

        mock_claude.side_effect = mock_call_claude_side_effect

        from src.agent.nodes.draft_email_generator import draft_email_generator

        result = await draft_email_generator(qual_state_pursue_now)

        # First contact failed, second should succeed
        assert len(result["draft_emails"]) == 1
        assert result["draft_emails"][0].contact_name == "James Park"


@pytest.mark.asyncio
async def test_draft_email_generator_no_account():
    """Should return empty drafts when no current_account."""
    state: QualificationState = {
        "thread_id": "test-thread",
        "workspace_id": "ws-test-001",
    }

    from src.agent.nodes.draft_email_generator import draft_email_generator

    result = await draft_email_generator(state)
    assert result["draft_emails"] == []


# ---------------------------------------------------------------------------
# Auto-outbound gate — draft-only mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_outbound_gate_draft_only_mode(mock_settings, mock_redis):
    """In draft-only mode, should NOT enqueue to outbound graph."""
    mock_settings.OUTBOUND_DRAFT_ONLY = True

    from src.agent.nodes.auto_outbound_gate import init_guardrails

    # Setup mock guardrails
    mock_kill_switch = AsyncMock()
    mock_kill_switch.is_paused = AsyncMock(return_value=(False, ""))
    mock_blocklist = AsyncMock()
    mock_blocklist.is_blocked = AsyncMock(return_value=(False, ""))
    mock_send_caps = AsyncMock()
    mock_send_caps.check_and_increment = AsyncMock()

    with patch("src.agent.nodes.auto_outbound_gate.settings", mock_settings), \
         patch("src.agent.nodes.auto_outbound_gate._kill_switch", mock_kill_switch), \
         patch("src.agent.nodes.auto_outbound_gate._blocklist", mock_blocklist), \
         patch("src.agent.nodes.auto_outbound_gate._send_caps", mock_send_caps), \
         patch("src.agent.nodes.auto_outbound_gate._clickhouse", None), \
         patch("src.agent.nodes.auto_outbound_gate.enqueue_by_event", new_callable=AsyncMock) as mock_enqueue:

        from src.agent.nodes.auto_outbound_gate import auto_outbound_gate

        state: QualificationState = {
            "thread_id": "test-thread",
            "workspace_id": "ws-test-001",
            "current_account": Account(
                id="acct-001",
                workspace_id="ws-test-001",
                company_name="TestCo",
                domain="testco.com",
            ),
            "campaign": MagicMock(
                sequence_config={"automation": {"enabled": True}},
            ),
            "action_recommendation": ActionRecommendation(
                action=ActionType.PURSUE_NOW,
                explanation="High fit",
                confidence_score=0.9,
            ),
            "account_score": AccountScore(
                account_id="acct-001",
                workspace_id="ws-test-001",
                icp_fit_score=90,
                pain_fit_score=85,
                timing_score=80,
                overall_priority_score=88,
                confidence_score=0.85,
            ),
            "ranked_contacts": [
                RankedContact(
                    contact_id="ct-001",
                    name="Alice",
                    title="VP Sales",
                    normalized_function="sales",
                    normalized_seniority="vp",
                    relevance_score=90,
                    likely_role=BuyingRole.PAIN_OWNER,
                    reason_for_relevance="Decision maker",
                ),
            ],
            "pain_hypotheses": [
                PainHypothesis(
                    pain_type=PainType.PRICING_COMPLEXITY,
                    score=80,
                    confidence_score=0.8,
                ),
                PainHypothesis(
                    pain_type=PainType.QUOTE_TO_CASH_FRICTION,
                    score=70,
                    confidence_score=0.7,
                ),
            ],
            "signals": [
                MagicMock(), MagicMock(),
            ],
            "seller_brief": SellerBrief(
                id="brief-001",
                account_id="acct-001",
                workspace_id="ws-test-001",
                account_snapshot="",
                why_this_account="",
                why_now="",
                likely_pain_points=[],
                recommended_contacts=[],
                persona_angles=[],
                risks_and_unknowns=["one unknown"],
                recommended_action=ActionRecommendation(
                    action=ActionType.PURSUE_NOW,
                    explanation="Pursue",
                ),
                generated_at=datetime.now(timezone.utc),
            ),
        }

        result = await auto_outbound_gate(state)

        assert result["auto_outbound_triggered"] is True
        # Should NOT have enqueued to outbound graph
        mock_enqueue.assert_not_called()
