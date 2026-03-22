"""Integration test fixtures — require docker compose services running.

Provides real database sessions, ClickHouse clients, and sample domain objects
for end-to-end testing against backing services.

Run with: uv run pytest tests/integration/ --integration -v
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.db.queries import Base


# ---------------------------------------------------------------------------
# pytest hooks — skip integration tests unless --integration is passed
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests against real backing services",
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --integration flag is passed."""
    if not config.getoption("--integration", default=False):
        skip = pytest.mark.skip(reason="need --integration flag to run")
        for item in items:
            if "integration" in str(item.fspath):
                item.add_marker(skip)


# ---------------------------------------------------------------------------
# Database engine & session
# ---------------------------------------------------------------------------

# Use CMO_DATABASE_URL from env, or default to direct PostgreSQL on port 5432
# (bypassing PgBouncer for tests so we can use CREATE TABLE / DDL).
_TEST_DATABASE_URL = os.environ.get(
    "CMO_DATABASE_URL",
    "postgresql+asyncpg://cmo:cmo_secret@localhost:5432/cmo",
)


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create an async engine pointing to the test database.

    Uses NullPool as per project rules (PgBouncer manages connections).
    Scoped to session so the engine is reused across all integration tests.
    """
    try:
        engine = create_async_engine(
            _TEST_DATABASE_URL,
            poolclass=NullPool,
            echo=False,
        )
        # Quick connectivity check
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        yield engine
    except Exception as exc:
        pytest.skip(f"PostgreSQL not available: {exc}")
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def setup_tables(db_engine):
    """Create all ORM tables before the test session; drop after.

    This ensures the schema is present even if the init.sql hasn't run
    or the DB was freshly created.
    """
    # Import all models so Base.metadata knows about them
    from src.db.campaign_memory import CampaignMemory  # noqa: F401
    from src.db.queries import (  # noqa: F401
        Account,
        AccountScoreRecord,
        Campaign,
        Contact,
        FeedbackEventRecord,
        Message,
        OutcomeEventRecord,
        PainHypothesisRecord,
        SellerBriefRecord,
        SignalRecord,
        WorkspaceSettings,
    )

    async with db_engine.begin() as conn:
        # Enable pgvector extension (required for campaign_memory)
        await conn.execute(
            __import__("sqlalchemy").text(
                "CREATE EXTENSION IF NOT EXISTS vector"
            )
        )
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db_session(db_engine, setup_tables):
    """Yield an AsyncSession that rolls back after each test.

    This keeps each test isolated — no data leaks between tests.
    """
    session_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        async with session.begin():
            yield session
            # Rollback after test completes — no permanent writes
            await session.rollback()


# ---------------------------------------------------------------------------
# Unique workspace ID per test
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace_id() -> str:
    """Generate a unique workspace_id for each test to avoid cross-contamination."""
    return f"ws-integ-{uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Sample domain objects
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_account(workspace_id: str):
    """Return a Pydantic Account model instance with the test workspace_id."""
    from src.agent.state import Account

    return Account(
        id=f"acct-{uuid4().hex[:8]}",
        workspace_id=workspace_id,
        company_name="IntegTest Corp",
        domain="integtest.com",
        industry="SaaS",
        employee_count=300,
        revenue=25_000_000.0,
        metadata={
            "geography": "US",
            "signals": ["recent_funding", "pricing_page_change"],
            "plan": "enterprise",
        },
    )


@pytest.fixture()
def sample_contacts(workspace_id: str, sample_account):
    """Return a list of Contact model instances tied to the sample account."""
    from src.agent.state import Contact

    return [
        Contact(
            id=f"contact-{uuid4().hex[:8]}",
            workspace_id=workspace_id,
            account_id=sample_account.id,
            email="cto@integtest.com",
            first_name="Alice",
            last_name="Chen",
            role="CTO",
        ),
        Contact(
            id=f"contact-{uuid4().hex[:8]}",
            workspace_id=workspace_id,
            account_id=sample_account.id,
            email="vp-revops@integtest.com",
            first_name="Bob",
            last_name="Martinez",
            role="VP Revenue Operations",
        ),
        Contact(
            id=f"contact-{uuid4().hex[:8]}",
            workspace_id=workspace_id,
            account_id=sample_account.id,
            email="head-pricing@integtest.com",
            first_name="Carla",
            last_name="Johansson",
            role="Head of Pricing",
        ),
    ]


@pytest.fixture()
def sample_campaign(workspace_id: str):
    """Return a Campaign model instance with the test workspace_id."""
    from src.agent.state import Campaign

    return Campaign(
        id=f"camp-{uuid4().hex[:8]}",
        workspace_id=workspace_id,
        name="Integration Test Campaign",
        status="active",
        icp_criteria={
            "industries": ["SaaS", "B2B Software"],
            "company_size": {"min": 50, "max": 5000},
            "revenue_range": {"min": 5_000_000, "max": 500_000_000},
        },
        sequence_config={"stages": 3, "delay_days": 3},
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# ClickHouse client fixture
# ---------------------------------------------------------------------------

_TEST_CLICKHOUSE_URL = os.environ.get(
    "CMO_CLICKHOUSE_URL",
    "clickhouse://localhost:9000/cmo",
)


@pytest_asyncio.fixture()
async def clickhouse_client():
    """Return a ClickHouseClient instance pointing to the test ClickHouse.

    Skips if ClickHouse is not available.
    """
    from src.db.clickhouse import ClickHouseClient

    client = ClickHouseClient(url=_TEST_CLICKHOUSE_URL)
    try:
        # Connectivity check
        sync_client = client._get_client()
        sync_client.execute("SELECT 1")
    except Exception as exc:
        pytest.skip(f"ClickHouse not available: {exc}")

    yield client
