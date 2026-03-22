"""Request/response Pydantic models for the API layer.

These are API-specific schemas — domain models live in src/agent/state.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Campaign schemas
# ---------------------------------------------------------------------------


class CreateCampaignRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    icp_criteria: dict[str, Any] = Field(default_factory=dict)
    sequence_config: dict[str, Any] = Field(default_factory=dict)


class CreateCampaignResponse(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime


class CampaignDetailResponse(BaseModel):
    id: str
    name: str
    status: str
    icp_criteria: dict[str, Any] | None = None
    sequence_config: dict[str, Any] | None = None
    created_at: datetime
    accounts_count: int = 0
    messages_sent: int = 0
    replies_count: int = 0


class TriggerCampaignRequest(BaseModel):
    campaign_id: str


# ---------------------------------------------------------------------------
# Webhook schemas
# ---------------------------------------------------------------------------


class WebhookPayload(BaseModel):
    event_type: str
    payload: dict[str, Any]
    workspace_id: str
    timestamp: datetime | None = None


class ApprovalResponse(BaseModel):
    thread_id: str
    approved: bool
    reviewer: str


# ---------------------------------------------------------------------------
# Report schemas
# ---------------------------------------------------------------------------


class ReportRequest(BaseModel):
    campaign_id: str
    date_from: datetime
    date_to: datetime


class ReportResponse(BaseModel):
    campaign_id: str
    period: str
    total_sent: int = 0
    total_replies: int = 0
    positive_replies: int = 0
    open_rate: float = 0.0
    reply_rate: float = 0.0
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Health schemas
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


# ---------------------------------------------------------------------------
# OmniGTM Qualification schemas
# ---------------------------------------------------------------------------


class AccountScoreRequest(BaseModel):
    account_ids: list[str] = Field(default_factory=list)
    campaign_id: str | None = None
    icp_overrides: dict[str, Any] = Field(default_factory=dict)


class EvidenceResponse(BaseModel):
    statement: str
    evidence_type: str
    source: str
    confidence: float = 0.0


class AccountScoreResponse(BaseModel):
    account_id: str
    icp_fit_score: int
    pain_fit_score: int
    timing_score: int
    overall_priority_score: int
    fit_reasons: list[EvidenceResponse] = Field(default_factory=list)
    non_fit_reasons: list[EvidenceResponse] = Field(default_factory=list)
    confidence_score: float = 0.0
    is_disqualified: bool = False
    disqualify_reason: str | None = None


class AccountScoreListResponse(BaseModel):
    scores: list[AccountScoreResponse]
    scoring_version: str = "v1"
    scored_at: datetime


class ContactRankRequest(BaseModel):
    account_id: str


class RankedContactResponse(BaseModel):
    contact_id: str
    name: str
    title: str
    normalized_function: str
    normalized_seniority: str
    relevance_score: int
    likely_role: str
    reason_for_relevance: str
    confidence_score: float = 0.0


class BuyingCommitteeResponse(BaseModel):
    account_id: str
    buying_committee: list[RankedContactResponse]
    committee_confidence: float = 0.0


class SignalIngestRequest(BaseModel):
    account_id: str
    signals: list[dict[str, Any]]


class SignalResponse(BaseModel):
    id: str
    signal_type: str
    observed_fact: str
    possible_implication: str
    confidence: float = 0.0
    source: str


class SignalIngestResponse(BaseModel):
    ingested: int
    signals: list[SignalResponse]


class PainHypothesisResponse(BaseModel):
    pain_type: str
    score: int
    supporting_facts: list[EvidenceResponse] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0


class PainInferenceResponse(BaseModel):
    account_id: str
    hypotheses: list[PainHypothesisResponse]


class ValuePropResponse(BaseModel):
    contact_id: str | None = None
    top_problem: str
    relevant_capability: str
    expected_business_outcome: str
    one_line_hook: str
    short_value_prop: str
    likely_objection: str
    suggested_response: str
    confidence_score: float = 0.0


class ActionRecommendationResponse(BaseModel):
    action: str
    explanation: str
    best_first_contact: RankedContactResponse | None = None
    best_channel: str | None = None
    multi_threading_recommended: bool = False
    manager_approval_required: bool = False
    confidence_score: float = 0.0
    threshold_details: dict[str, Any] = Field(default_factory=dict)


class SellerBriefResponse(BaseModel):
    brief_id: str
    version: int = 1
    account_snapshot: str
    why_this_account: str
    why_now: str
    likely_pain_points: list[PainHypothesisResponse]
    recommended_contacts: list[RankedContactResponse]
    persona_angles: list[ValuePropResponse]
    risks_and_unknowns: list[str]
    recommended_action: ActionRecommendationResponse
    sources_consulted: list[str] = Field(default_factory=list)
    generated_at: datetime


class BriefGenerateRequest(BaseModel):
    campaign_id: str | None = None
    force_regenerate: bool = False


class QualifyBatchRequest(BaseModel):
    account_ids: list[str] = Field(default_factory=list)
    max_accounts: int = 50


class QualifyBatchResponse(BaseModel):
    job_id: str
    queue: str = "batch"
    accounts_queued: int


class FeedbackRequest(BaseModel):
    recommendation_id: str
    recommendation_type: str
    user_id: str
    action_taken: str
    correction: str | None = None


class FeedbackResponse(BaseModel):
    feedback_id: str
    recorded_at: datetime


# ---------------------------------------------------------------------------
# Automation control schemas
# ---------------------------------------------------------------------------


class AutomationPauseRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class AutomationStatusResponse(BaseModel):
    workspace_id: str
    is_paused: bool = False
    reason: str = ""
    global_pause: bool = False
    workspace_pause: bool = False
    daily_remaining: int = 0
    weekly_remaining: int = 0
    daily_used: int = 0
    weekly_used: int = 0
