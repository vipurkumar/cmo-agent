"""OutboundState TypedDict and ALL Pydantic models for the CMO Agent.

This is the ONLY place Pydantic models live. NEVER define models in tool
files, node files, or API files — import from here instead.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Pydantic models — data shapes flowing through the graph
# ---------------------------------------------------------------------------


class Account(BaseModel):
    id: str
    workspace_id: str
    company_name: str
    domain: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    revenue: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Contact(BaseModel):
    id: str
    workspace_id: str
    account_id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: str | None = None
    linkedin_url: str | None = None
    phone: str | None = None


class Campaign(BaseModel):
    id: str
    workspace_id: str
    name: str
    status: str = "active"
    icp_criteria: dict[str, Any] = Field(default_factory=dict)
    sequence_config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class Message(BaseModel):
    id: str
    workspace_id: str
    contact_id: str
    campaign_id: str
    subject: str | None = None
    body: str
    stage: int
    status: str = "draft"
    sent_at: datetime | None = None
    reply_text: str | None = None
    reply_intent: str | None = None


class EnrichmentResult(BaseModel):
    company_summary: str
    recent_news: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    personalization_hooks: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class PersonalizedEmail(BaseModel):
    subject_line: str
    body: str
    personalization_score: float = 0.0


class ReplyAnalysis(BaseModel):
    intent: Literal["positive", "negative", "neutral", "unsubscribe"]
    confidence: float = 0.0
    reasoning: str = ""
    suggested_action: str = ""


class SequenceStage(BaseModel):
    stage_number: int
    template_id: str
    delay_days: int = 0
    channel: Literal["email", "linkedin", "slack"] = "email"


# ---------------------------------------------------------------------------
# OmniGTM Agent — Enums
# ---------------------------------------------------------------------------


class EvidenceType(str, Enum):
    FACT = "fact"
    INFERENCE = "inference"
    UNKNOWN = "unknown"


class SignalType(str, Enum):
    PRICING_CHANGE = "pricing_change"
    USAGE_BASED_PRICING = "usage_based_pricing"
    INTERNATIONAL_EXPANSION = "international_expansion"
    ENTERPRISE_MOTION = "enterprise_motion"
    HIRING_REVOPS_PRICING = "hiring_revops_pricing"
    BILLING_CPQ_CHANGE = "billing_cpq_change"
    FUNDING = "funding"
    ACQUISITION = "acquisition"
    NEW_PRODUCT_LAUNCH = "new_product_launch"
    LEADERSHIP_CHANGE = "leadership_change"
    PARTNER_CHANNEL_MOTION = "partner_channel_motion"
    PUBLIC_FRICTION = "public_friction"


class PainType(str, Enum):
    PRICING_COMPLEXITY = "pricing_complexity"
    PACKAGING_INCONSISTENCY = "packaging_inconsistency"
    QUOTE_TO_CASH_FRICTION = "quote_to_cash_friction"
    DISCOUNTING_GOVERNANCE = "discounting_governance"
    BILLING_MISMATCH = "billing_mismatch"
    MONETIZATION_VISIBILITY = "monetization_visibility"
    EXPANSION_PRICING = "expansion_pricing"
    ENTITLEMENT_GOVERNANCE = "entitlement_governance"


class BuyingRole(str, Enum):
    ECONOMIC_BUYER = "economic_buyer"
    PAIN_OWNER = "pain_owner"
    OPERATOR = "operator"
    TECHNICAL_EVALUATOR = "technical_evaluator"
    EXECUTIVE_SPONSOR = "executive_sponsor"
    BLOCKER = "blocker"
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    PURSUE_NOW = "pursue_now"
    NURTURE = "nurture"
    DISQUALIFY = "disqualify"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


# ---------------------------------------------------------------------------
# OmniGTM Agent — Evidence tracking
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    statement: str
    evidence_type: EvidenceType
    source: str
    source_url: str | None = None
    observed_at: datetime | None = None
    confidence: float = 0.0
    freshness_days: int | None = None


# ---------------------------------------------------------------------------
# OmniGTM Agent — Account Scoring
# ---------------------------------------------------------------------------


class AccountScore(BaseModel):
    account_id: str
    workspace_id: str
    icp_fit_score: int  # 0–100
    pain_fit_score: int  # 0–100
    timing_score: int  # 0–100
    overall_priority_score: int  # 0–100
    fit_reasons: list[Evidence] = Field(default_factory=list)
    non_fit_reasons: list[Evidence] = Field(default_factory=list)
    confidence_score: float = 0.0
    is_disqualified: bool = False
    disqualify_reason: str | None = None
    scoring_version: str = "v1"
    scored_at: datetime | None = None


# ---------------------------------------------------------------------------
# OmniGTM Agent — Contact / Buying Committee
# ---------------------------------------------------------------------------


class RankedContact(BaseModel):
    contact_id: str
    name: str
    title: str
    normalized_function: str
    normalized_seniority: str
    relevance_score: int  # 0–100
    likely_role: BuyingRole
    reason_for_relevance: str
    confidence_score: float = 0.0
    evidence: list[Evidence] = Field(default_factory=list)


class BuyingCommittee(BaseModel):
    account_id: str
    workspace_id: str
    ranked_contacts: list[RankedContact] = Field(default_factory=list)
    committee_confidence: float = 0.0
    mapped_at: datetime | None = None


# ---------------------------------------------------------------------------
# OmniGTM Agent — Signals
# ---------------------------------------------------------------------------


class Signal(BaseModel):
    id: str
    account_id: str
    workspace_id: str
    signal_type: SignalType
    source: str
    observed_fact: str
    possible_implication: str
    event_date: datetime | None = None
    recency_score: float = 0.0
    reliability_score: float = 0.0
    confidence: float = 0.0
    source_url: str | None = None


# ---------------------------------------------------------------------------
# OmniGTM Agent — Pain Hypotheses
# ---------------------------------------------------------------------------


class PainHypothesis(BaseModel):
    pain_type: PainType
    score: int  # 0–100
    supporting_facts: list[Evidence] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0


# ---------------------------------------------------------------------------
# OmniGTM Agent — Value Proposition
# ---------------------------------------------------------------------------


class ValuePropRecommendation(BaseModel):
    contact_id: str | None = None
    top_problem: str
    relevant_capability: str
    expected_business_outcome: str
    one_line_hook: str
    short_value_prop: str
    likely_objection: str
    suggested_response: str
    proof_point: Evidence | None = None
    confidence_score: float = 0.0


# ---------------------------------------------------------------------------
# OmniGTM Agent — Action Recommendation
# ---------------------------------------------------------------------------


class ActionRecommendation(BaseModel):
    action: ActionType
    explanation: str
    best_first_contact: RankedContact | None = None
    best_channel: str | None = None
    multi_threading_recommended: bool = False
    manager_approval_required: bool = False
    confidence_score: float = 0.0
    threshold_details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# OmniGTM Agent — Seller Brief
# ---------------------------------------------------------------------------


class SellerBrief(BaseModel):
    id: str
    account_id: str
    workspace_id: str
    version: int = 1
    account_snapshot: str
    why_this_account: str
    why_now: str
    likely_pain_points: list[PainHypothesis]
    recommended_contacts: list[RankedContact]
    persona_angles: list[ValuePropRecommendation]
    risks_and_unknowns: list[str]
    recommended_action: ActionRecommendation
    signals_used: list[Signal] = Field(default_factory=list)
    sources_consulted: list[str] = Field(default_factory=list)
    scoring: AccountScore | None = None
    generated_at: datetime | None = None
    model_version: str = "v1"
    prompt_version: str = "v1"


# ---------------------------------------------------------------------------
# OmniGTM Agent — Feedback & Outcomes
# ---------------------------------------------------------------------------


class FeedbackEvent(BaseModel):
    id: str
    workspace_id: str
    recommendation_id: str
    recommendation_type: str
    user_id: str
    action_taken: str
    correction: str | None = None
    model_version: str = "v1"
    created_at: datetime | None = None


class OutcomeEvent(BaseModel):
    id: str
    workspace_id: str
    account_id: str
    opportunity_id: str | None = None
    event_type: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# LangGraph state — Outbound execution (existing)
# ---------------------------------------------------------------------------


class OutboundState(TypedDict, total=False):
    thread_id: str
    workspace_id: str
    campaign: Campaign
    accounts: list[Account]
    current_account: Account | None
    contacts: list[Contact]
    current_contact: Contact | None
    enrichment: EnrichmentResult | None
    draft_email: PersonalizedEmail | None
    approval_status: str | None
    sent_messages: list[Message]
    reply_analysis: ReplyAnalysis | None
    current_stage: int
    max_stages: int
    error: str | None
    should_continue: bool


# ---------------------------------------------------------------------------
# LangGraph state — Qualification intelligence (OmniGTM)
# ---------------------------------------------------------------------------


class QualificationState(TypedDict, total=False):
    thread_id: str
    workspace_id: str
    campaign: Campaign

    # Batch processing
    raw_accounts: list[dict]
    accounts: list[Account]
    current_account: Account | None

    # Per-account intelligence
    contacts: list[Contact]
    ranked_contacts: list[RankedContact]
    buying_committee: BuyingCommittee | None
    signals: list[Signal]
    pain_hypotheses: list[PainHypothesis]
    value_props: list[ValuePropRecommendation]
    account_score: AccountScore | None
    seller_brief: SellerBrief | None
    action_recommendation: ActionRecommendation | None

    # Knowledge base context
    kb_case_studies: list[str]
    kb_battlecards: list[str]
    kb_messaging: list[str]

    # Control flow
    current_stage: int
    approval_status: str | None
    error: str | None
    should_continue: bool

    # Phase 4: Automation
    auto_outbound_triggered: bool
    auto_outbound_skip_reason: str | None
