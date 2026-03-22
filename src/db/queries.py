"""Typed async database query functions.

ALL database writes go through this module. Every query MUST include
a workspace_id filter for tenant isolation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from src.config import settings
from src.logger import log

# ---------------------------------------------------------------------------
# Engine & session factory — NullPool because PgBouncer manages connections
# ---------------------------------------------------------------------------

engine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
    echo=False,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# ORM base & models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    icp_criteria: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    sequence_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    contact_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    settings_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Query functions — workspace_id is MANDATORY on every query
# ---------------------------------------------------------------------------


async def get_campaign(
    session: AsyncSession,
    campaign_id: str,
    workspace_id: str,
) -> Campaign | None:
    """Fetch a single campaign by id, scoped to workspace."""
    log.debug("db.get_campaign", campaign_id=campaign_id, workspace_id=workspace_id)
    result = await session.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .where(Campaign.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


async def create_campaign(
    session: AsyncSession,
    workspace_id: str,
    name: str,
    icp_criteria: dict[str, Any] | None = None,
    sequence_config: dict[str, Any] | None = None,
) -> Campaign:
    """Create a new campaign in the given workspace."""
    log.info("db.create_campaign", workspace_id=workspace_id, name=name)
    campaign = Campaign(
        workspace_id=workspace_id,
        name=name,
        icp_criteria=icp_criteria,
        sequence_config=sequence_config,
    )
    session.add(campaign)
    await session.flush()
    return campaign


async def list_campaigns(
    session: AsyncSession,
    workspace_id: str,
) -> Sequence[Campaign]:
    """List all campaigns for a workspace."""
    log.debug("db.list_campaigns", workspace_id=workspace_id)
    result = await session.execute(
        select(Campaign)
        .where(Campaign.workspace_id == workspace_id)
        .order_by(Campaign.created_at.desc())
    )
    return result.scalars().all()


async def get_account(
    session: AsyncSession,
    account_id: str,
    workspace_id: str,
) -> Account | None:
    """Fetch a single account by id, scoped to workspace."""
    log.debug("db.get_account", account_id=account_id, workspace_id=workspace_id)
    result = await session.execute(
        select(Account)
        .where(Account.id == account_id)
        .where(Account.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


async def create_account(
    session: AsyncSession,
    workspace_id: str,
    company_name: str,
    domain: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Account:
    """Create a new account in the given workspace."""
    log.info("db.create_account", workspace_id=workspace_id, company_name=company_name)
    account = Account(
        workspace_id=workspace_id,
        company_name=company_name,
        domain=domain,
        metadata_=metadata,
    )
    session.add(account)
    await session.flush()
    return account


async def get_contacts_for_account(
    session: AsyncSession,
    account_id: str,
    workspace_id: str,
) -> Sequence[Contact]:
    """Fetch all contacts belonging to an account, scoped to workspace."""
    log.debug("db.get_contacts_for_account", account_id=account_id, workspace_id=workspace_id)
    result = await session.execute(
        select(Contact)
        .where(Contact.account_id == account_id)
        .where(Contact.workspace_id == workspace_id)
    )
    return result.scalars().all()


async def create_contact(
    session: AsyncSession,
    workspace_id: str,
    account_id: str,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
    role: str | None = None,
) -> Contact:
    """Create a new contact in the given workspace."""
    log.info("db.create_contact", workspace_id=workspace_id, email=email)
    contact = Contact(
        workspace_id=workspace_id,
        account_id=account_id,
        email=email,
        first_name=first_name,
        last_name=last_name,
        role=role,
    )
    session.add(contact)
    await session.flush()
    return contact


async def save_message(
    session: AsyncSession,
    workspace_id: str,
    contact_id: str,
    campaign_id: str,
    subject: str | None,
    body: str,
    stage: str,
) -> Message:
    """Persist an outbound message draft."""
    log.info(
        "db.save_message",
        workspace_id=workspace_id,
        contact_id=contact_id,
        campaign_id=campaign_id,
        stage=stage,
    )
    message = Message(
        workspace_id=workspace_id,
        contact_id=contact_id,
        campaign_id=campaign_id,
        subject=subject,
        body=body,
        stage=stage,
        status="draft",
    )
    session.add(message)
    await session.flush()
    return message


async def update_message_status(
    session: AsyncSession,
    message_id: str,
    workspace_id: str,
    status: str,
) -> None:
    """Update the delivery status of a message, scoped to workspace."""
    log.info(
        "db.update_message_status",
        message_id=message_id,
        workspace_id=workspace_id,
        status=status,
    )
    await session.execute(
        update(Message)
        .where(Message.id == message_id)
        .where(Message.workspace_id == workspace_id)
        .values(status=status)
    )
    await session.flush()


async def get_workspace_settings(
    session: AsyncSession,
    workspace_id: str,
) -> WorkspaceSettings | None:
    """Fetch workspace-level settings."""
    log.debug("db.get_workspace_settings", workspace_id=workspace_id)
    result = await session.execute(
        select(WorkspaceSettings)
        .where(WorkspaceSettings.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# OmniGTM ORM models
# ---------------------------------------------------------------------------


class AccountScoreRecord(Base):
    __tablename__ = "account_scores"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    icp_fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    pain_fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    timing_score: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_priority_score: Mapped[int] = mapped_column(Integer, nullable=False)
    fit_reasons: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    non_fit_reasons: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_disqualified: Mapped[bool] = mapped_column(default=False)
    disqualify_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    scoring_version: Mapped[str] = mapped_column(String, default="v1")
    scored_at = Column(DateTime(timezone=True), server_default=func.now())


class SignalRecord(Base):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    observed_fact: Mapped[str] = mapped_column(Text, nullable=False)
    possible_implication: Mapped[str] = mapped_column(Text, nullable=False)
    event_date = Column(DateTime(timezone=True), nullable=True)
    recency_score: Mapped[float] = mapped_column(Float, default=0.0)
    reliability_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PainHypothesisRecord(Base):
    __tablename__ = "pain_hypotheses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    brief_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    pain_type: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    supporting_facts: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    inferences: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    unknowns: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SellerBriefRecord(Base):
    __tablename__ = "seller_briefs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    brief_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String, default="v1")
    prompt_version: Mapped[str] = mapped_column(String, default="v1")
    generated_at = Column(DateTime(timezone=True), server_default=func.now())


class FeedbackEventRecord(Base):
    __tablename__ = "feedback_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    recommendation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    recommendation_type: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    action_taken: Mapped[str] = mapped_column(String, nullable=False)
    correction: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str] = mapped_column(String, default="v1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OutcomeEventRecord(Base):
    __tablename__ = "outcome_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# OmniGTM query functions — workspace_id MANDATORY on every query
# ---------------------------------------------------------------------------


async def save_account_score(
    session: AsyncSession,
    workspace_id: str,
    account_id: str,
    icp_fit_score: int,
    pain_fit_score: int,
    timing_score: int,
    overall_priority_score: int,
    confidence_score: float,
    fit_reasons: list[dict] | None = None,
    non_fit_reasons: list[dict] | None = None,
    is_disqualified: bool = False,
    disqualify_reason: str | None = None,
) -> AccountScoreRecord:
    """Persist an account score, scoped to workspace."""
    log.info("db.save_account_score", workspace_id=workspace_id, account_id=account_id)
    record = AccountScoreRecord(
        workspace_id=workspace_id,
        account_id=account_id,
        icp_fit_score=icp_fit_score,
        pain_fit_score=pain_fit_score,
        timing_score=timing_score,
        overall_priority_score=overall_priority_score,
        confidence_score=confidence_score,
        fit_reasons=fit_reasons,
        non_fit_reasons=non_fit_reasons,
        is_disqualified=is_disqualified,
        disqualify_reason=disqualify_reason,
    )
    session.add(record)
    await session.flush()
    return record


async def get_account_score(
    session: AsyncSession,
    account_id: str,
    workspace_id: str,
) -> AccountScoreRecord | None:
    """Fetch the latest score for an account."""
    log.debug("db.get_account_score", account_id=account_id, workspace_id=workspace_id)
    result = await session.execute(
        select(AccountScoreRecord)
        .where(AccountScoreRecord.account_id == account_id)
        .where(AccountScoreRecord.workspace_id == workspace_id)
        .order_by(AccountScoreRecord.scored_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def save_signal(
    session: AsyncSession,
    workspace_id: str,
    account_id: str,
    signal_type: str,
    source: str,
    observed_fact: str,
    possible_implication: str,
    confidence: float,
    reliability_score: float = 0.0,
    recency_score: float = 0.0,
    event_date: Any = None,
    source_url: str | None = None,
) -> SignalRecord:
    """Persist a detected signal."""
    log.info("db.save_signal", workspace_id=workspace_id, account_id=account_id, signal_type=signal_type)
    record = SignalRecord(
        workspace_id=workspace_id,
        account_id=account_id,
        signal_type=signal_type,
        source=source,
        observed_fact=observed_fact,
        possible_implication=possible_implication,
        confidence=confidence,
        reliability_score=reliability_score,
        recency_score=recency_score,
        event_date=event_date,
        source_url=source_url,
    )
    session.add(record)
    await session.flush()
    return record


async def get_signals_for_account(
    session: AsyncSession,
    account_id: str,
    workspace_id: str,
) -> Sequence[SignalRecord]:
    """Fetch all signals for an account, ordered by recency."""
    log.debug("db.get_signals", account_id=account_id, workspace_id=workspace_id)
    result = await session.execute(
        select(SignalRecord)
        .where(SignalRecord.account_id == account_id)
        .where(SignalRecord.workspace_id == workspace_id)
        .order_by(SignalRecord.created_at.desc())
    )
    return result.scalars().all()


async def save_seller_brief(
    session: AsyncSession,
    workspace_id: str,
    account_id: str,
    brief_json: dict[str, Any],
    action_type: str,
    overall_score: int,
    confidence_score: float,
    version: int = 1,
) -> SellerBriefRecord:
    """Persist a seller brief."""
    log.info("db.save_seller_brief", workspace_id=workspace_id, account_id=account_id)
    record = SellerBriefRecord(
        workspace_id=workspace_id,
        account_id=account_id,
        brief_json=brief_json,
        action_type=action_type,
        overall_score=overall_score,
        confidence_score=confidence_score,
        version=version,
    )
    session.add(record)
    await session.flush()
    return record


async def get_seller_brief(
    session: AsyncSession,
    account_id: str,
    workspace_id: str,
) -> SellerBriefRecord | None:
    """Fetch the latest seller brief for an account."""
    log.debug("db.get_seller_brief", account_id=account_id, workspace_id=workspace_id)
    result = await session.execute(
        select(SellerBriefRecord)
        .where(SellerBriefRecord.account_id == account_id)
        .where(SellerBriefRecord.workspace_id == workspace_id)
        .order_by(SellerBriefRecord.generated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def save_feedback_event(
    session: AsyncSession,
    workspace_id: str,
    recommendation_id: str,
    recommendation_type: str,
    user_id: str,
    action_taken: str,
    correction: str | None = None,
) -> FeedbackEventRecord:
    """Capture a feedback event on a recommendation."""
    log.info("db.save_feedback", workspace_id=workspace_id, recommendation_id=recommendation_id)
    record = FeedbackEventRecord(
        workspace_id=workspace_id,
        recommendation_id=recommendation_id,
        recommendation_type=recommendation_type,
        user_id=user_id,
        action_taken=action_taken,
        correction=correction,
    )
    session.add(record)
    await session.flush()
    return record


async def save_outcome_event(
    session: AsyncSession,
    workspace_id: str,
    account_id: str,
    event_type: str,
    opportunity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> OutcomeEventRecord:
    """Record a business outcome event."""
    log.info("db.save_outcome", workspace_id=workspace_id, account_id=account_id, event_type=event_type)
    record = OutcomeEventRecord(
        workspace_id=workspace_id,
        account_id=account_id,
        event_type=event_type,
        opportunity_id=opportunity_id,
        details=details,
    )
    session.add(record)
    await session.flush()
    return record


async def list_seller_briefs_by_action(
    session: AsyncSession,
    workspace_id: str,
    action_type: str,
    limit: int = 50,
) -> Sequence[SellerBriefRecord]:
    """List seller briefs filtered by action type (e.g. 'pursue_now')."""
    log.debug("db.list_briefs_by_action", workspace_id=workspace_id, action_type=action_type)
    result = await session.execute(
        select(SellerBriefRecord)
        .where(SellerBriefRecord.workspace_id == workspace_id)
        .where(SellerBriefRecord.action_type == action_type)
        .order_by(SellerBriefRecord.overall_score.desc())
        .limit(limit)
    )
    return result.scalars().all()
