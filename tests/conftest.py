"""Shared fixtures for the CMO Agent test suite.

All tests are fast, fully mocked, and make zero network calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.state import (
    Account,
    AccountScore,
    ActionRecommendation,
    ActionType,
    BuyingRole,
    Campaign,
    Contact,
    EnrichmentResult,
    Evidence,
    EvidenceType,
    OutboundState,
    PainHypothesis,
    PainType,
    QualificationState,
    RankedContact,
    SellerBrief,
    Signal,
    SignalType,
    ValuePropRecommendation,
)


# ---------------------------------------------------------------------------
# Settings — patched for every test so nothing touches real services
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_settings():
    """Return a MagicMock ``settings`` object with safe test values.

    Callers must patch ``settings`` in every module that imports it, e.g.::

        with patch("src.tools.apollo_search.settings", mock_settings):
            ...

    The fixture itself does NOT auto-patch any module — that is intentional
    so each test controls exactly which modules see the mock.
    """
    fake = MagicMock()
    fake.CLAUDE_MODEL = "claude-sonnet-4-6"
    fake.CLAUDE_HAIKU_MODEL = "claude-haiku-4-5-20251001"
    fake.ANTHROPIC_API_KEY = "test-anthropic-key"
    fake.DATABASE_URL = "postgresql+asyncpg://localhost:6432/cmo_test"
    fake.REDIS_URL = "redis://localhost:6379/15"
    fake.REDIS_KEY_PREFIX = "cmo_test:"
    fake.CLICKHOUSE_URL = "clickhouse://localhost:9000/cmo_test"
    fake.HMAC_SECRET = "test-hmac-secret"
    fake.N8N_WEBHOOK_BASE_URL = "http://localhost:5678/webhook"
    fake.MAX_ACCOUNTS_PER_BATCH = 20
    fake.SEQUENCE_MAX_STAGES = 3
    fake.APOLLO_API_KEY = "test-apollo-key"
    fake.APOLLO_BASE_URL = "https://api.apollo.io/v1"
    fake.CLAY_API_KEY = "test-clay-key"
    fake.CLAY_BASE_URL = "https://api.clay.com/v1"
    fake.HOST = "0.0.0.0"
    fake.PORT = 8000
    fake.LOG_LEVEL = "debug"
    fake.EMBEDDING_PROVIDER = "anthropic"
    fake.EMBEDDING_MODEL = "voyage-3"
    fake.EMBEDDING_DIMENSIONS = 1024
    fake.OPENAI_API_KEY = ""
    fake.USE_APOLLO_ENRICHMENT = False
    fake.APOLLO_MCP_ENABLED = False
    fake.USE_CLAY_ENRICHMENT = False
    fake.OUTBOUND_DRAFT_ONLY = True
    fake.DEMO_MODE = False
    fake.SLACK_BOT_TOKEN = "xoxb-test"
    fake.SLACK_SIGNING_SECRET = "test-signing-secret"
    fake.HUBSPOT_API_KEY = "test-hubspot-key"
    fake.ZOHO_CLIENT_ID = "test-zoho-client"
    fake.ZOHO_CLIENT_SECRET = "test-zoho-secret"
    fake.ZOHO_REFRESH_TOKEN = "test-zoho-refresh"
    fake.LINKEDIN_API_KEY = "test-linkedin-key"
    fake.N8N_WEBHOOK_BASE_URL = "http://localhost:5678/webhook"
    return fake


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_redis():
    """AsyncMock Redis client."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=1)
    redis.eval = AsyncMock(return_value=1)
    redis.register_script = MagicMock(return_value=AsyncMock(return_value=[9, 0]))
    return redis


# ---------------------------------------------------------------------------
# SQLAlchemy async session
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_session():
    """AsyncMock SQLAlchemy AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_rate_limiter():
    """AsyncMock RateLimiter that always passes."""
    limiter = AsyncMock()
    limiter.enforce = AsyncMock(return_value=None)
    return limiter


# ---------------------------------------------------------------------------
# Domain model fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_account() -> Account:
    return Account(
        id="acct-001",
        workspace_id="ws-test-001",
        company_name="Acme Corp",
        domain="acme.com",
        industry="SaaS",
        employee_count=250,
        revenue=15_000_000.0,
        metadata={"plan": "pro"},
    )


@pytest.fixture()
def sample_contact(sample_account: Account) -> Contact:
    return Contact(
        id="contact-001",
        workspace_id=sample_account.workspace_id,
        account_id=sample_account.id,
        email="jane@acme.com",
        first_name="Jane",
        last_name="Doe",
        role="VP of Engineering",
        linkedin_url="https://linkedin.com/in/janedoe",
    )


@pytest.fixture()
def sample_campaign() -> Campaign:
    return Campaign(
        id="camp-001",
        workspace_id="ws-test-001",
        name="Q1 SaaS Outbound",
        status="active",
        icp_criteria={"industries": ["SaaS"], "employee_range": [50, 500]},
        sequence_config={"stages": 3, "delay_days": 3},
        created_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
    )


@pytest.fixture()
def sample_enrichment() -> EnrichmentResult:
    return EnrichmentResult(
        company_summary="Acme Corp is a mid-market SaaS company...",
        recent_news=["Acme raised Series B", "Acme launched new product"],
        pain_points=["Scaling outbound", "Manual prospecting"],
        personalization_hooks=["Series B momentum", "New product launch"],
        technologies=["Python", "AWS", "Salesforce"],
    )


@pytest.fixture()
def sample_state(
    sample_account: Account,
    sample_contact: Contact,
    sample_campaign: Campaign,
) -> OutboundState:
    """OutboundState populated with realistic test data."""
    return OutboundState(
        thread_id="thread-test-001",
        workspace_id="ws-test-001",
        campaign=sample_campaign,
        accounts=[sample_account],
        current_account=sample_account,
        contacts=[sample_contact],
        current_contact=sample_contact,
        enrichment=None,
        draft_email=None,
        approval_status=None,
        sent_messages=[],
        reply_analysis=None,
        current_stage=1,
        max_stages=3,
        error=None,
        should_continue=True,
    )


# ---------------------------------------------------------------------------
# Qualification pipeline fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_account_score(sample_account: Account) -> AccountScore:
    return AccountScore(
        account_id=sample_account.id,
        workspace_id=sample_account.workspace_id,
        icp_fit_score=85,
        pain_fit_score=70,
        timing_score=60,
        overall_priority_score=75,
        fit_reasons=[
            Evidence(
                statement="SaaS company in target segment",
                evidence_type=EvidenceType.FACT,
                source="icp_scorer",
                confidence=0.9,
            )
        ],
        non_fit_reasons=[],
        confidence_score=0.8,
        is_disqualified=False,
    )


@pytest.fixture()
def sample_ranked_contact() -> RankedContact:
    return RankedContact(
        contact_id="contact-001",
        name="Jane Doe",
        title="VP of Engineering",
        normalized_function="Engineering",
        normalized_seniority="VP",
        relevance_score=80,
        likely_role=BuyingRole.PAIN_OWNER,
        reason_for_relevance="Owns engineering budget and tooling decisions",
        confidence_score=0.8,
    )


@pytest.fixture()
def sample_pain_hypothesis() -> PainHypothesis:
    return PainHypothesis(
        pain_type=PainType.PRICING_COMPLEXITY,
        score=75,
        supporting_facts=[
            Evidence(
                statement="Multiple pricing tiers with complex add-ons",
                evidence_type=EvidenceType.FACT,
                source="pricing_page",
                confidence=0.85,
            )
        ],
        inferences=["Likely struggling with quote-to-cash"],
        unknowns=["Current billing platform unknown"],
        confidence_score=0.75,
    )


@pytest.fixture()
def sample_signal(sample_account: Account) -> Signal:
    return Signal(
        id="sig-001",
        account_id=sample_account.id,
        workspace_id=sample_account.workspace_id,
        signal_type=SignalType.FUNDING,
        source="news",
        observed_fact="Raised Series B",
        possible_implication="Growth phase, likely investing in tools",
        recency_score=0.9,
        reliability_score=0.8,
        confidence=0.85,
    )


@pytest.fixture()
def sample_qualification_state(
    sample_account: Account,
    sample_contact: Contact,
    sample_campaign: Campaign,
    sample_account_score: AccountScore,
    sample_ranked_contact: RankedContact,
    sample_pain_hypothesis: PainHypothesis,
    sample_signal: Signal,
) -> QualificationState:
    """QualificationState populated with realistic test data."""
    return QualificationState(
        thread_id="thread-qual-001",
        workspace_id="ws-test-001",
        campaign=sample_campaign,
        raw_accounts=[],
        accounts=[sample_account],
        current_account=sample_account,
        contacts=[sample_contact],
        ranked_contacts=[sample_ranked_contact],
        buying_committee=None,
        signals=[sample_signal],
        pain_hypotheses=[sample_pain_hypothesis],
        value_props=[],
        account_score=sample_account_score,
        seller_brief=None,
        action_recommendation=None,
        kb_case_studies=[],
        kb_battlecards=[],
        kb_messaging=[],
        current_stage=1,
        approval_status=None,
        error=None,
        should_continue=True,
        auto_outbound_triggered=False,
        auto_outbound_skip_reason=None,
    )
