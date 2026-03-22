"""Knowledge base integration tests — pgvector storage and retrieval.

Requires: docker compose up -d (PostgreSQL with pgvector)
Run with: uv run pytest tests/integration/ --integration -v

Tests embedding storage, similarity search, and KnowledgeBaseLoader.load_all().
"""

from __future__ import annotations

import math
from uuid import uuid4

import pytest
import pytest_asyncio

from src.db.campaign_memory import EMBEDDING_DIM, search_similar, store_embedding
from src.knowledge.loader import KnowledgeBaseLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_embedding(seed: float, dim: int = EMBEDDING_DIM) -> list[float]:
    """Generate a deterministic normalized embedding vector from a seed value.

    Different seeds produce different vectors, enabling similarity search testing.
    Uses sine/cosine pattern to create orthogonal-ish vectors for different seeds.
    """
    raw = [math.sin(seed * (i + 1)) for i in range(dim)]
    # L2 normalize so cosine distance is meaningful
    magnitude = math.sqrt(sum(x * x for x in raw))
    if magnitude == 0:
        return [0.0] * dim
    return [x / magnitude for x in raw]


# ---------------------------------------------------------------------------
# Store and search embedding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_and_search_embedding(db_session, workspace_id):
    """Store a document embedding, search with similar query, verify it comes back."""
    campaign_id = f"camp-kb-{uuid4().hex[:8]}"
    content = "Our pricing engine helps B2B SaaS companies monetize usage-based models."
    embedding = _make_embedding(seed=1.0)

    # Store
    memory = await store_embedding(
        session=db_session,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        content=content,
        embedding_vector=embedding,
    )
    assert memory.id is not None
    assert memory.content == content

    # Search with the same vector (should be the closest match)
    results = await search_similar(
        session=db_session,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        query_vector=embedding,
        top_k=5,
    )

    assert len(results) >= 1
    assert results[0].content == content


@pytest.mark.asyncio
async def test_search_returns_empty_for_unrelated(db_session, workspace_id):
    """Store pricing docs, search with an unrelated vector, verify low relevance."""
    campaign_id = f"camp-unrel-{uuid4().hex[:8]}"

    # Store a pricing-themed document
    await store_embedding(
        session=db_session,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        content="Enterprise pricing tiers with volume discounts and annual contracts.",
        embedding_vector=_make_embedding(seed=2.0),
    )

    # Search with a completely different campaign_id (no entries)
    other_campaign = f"camp-other-{uuid4().hex[:8]}"
    results = await search_similar(
        session=db_session,
        workspace_id=workspace_id,
        campaign_id=other_campaign,
        query_vector=_make_embedding(seed=99.0),
        top_k=5,
    )

    assert len(results) == 0, "Search in a different campaign scope should return nothing"


@pytest.mark.asyncio
async def test_search_respects_workspace_isolation(db_session):
    """Store embedding in workspace A, search from workspace B — should find nothing."""
    ws_a = f"ws-vec-a-{uuid4().hex[:8]}"
    ws_b = f"ws-vec-b-{uuid4().hex[:8]}"
    campaign_id = "camp-shared"
    embedding = _make_embedding(seed=3.0)

    await store_embedding(
        session=db_session,
        workspace_id=ws_a,
        campaign_id=campaign_id,
        content="Workspace A's secret competitive intel.",
        embedding_vector=embedding,
    )

    results = await search_similar(
        session=db_session,
        workspace_id=ws_b,
        campaign_id=campaign_id,
        query_vector=embedding,
        top_k=5,
    )

    assert len(results) == 0, "Tenant isolation violated in pgvector search"


@pytest.mark.asyncio
async def test_search_relevance_ordering(db_session, workspace_id):
    """Store 3 docs with different embeddings, search, verify most relevant comes first."""
    campaign_id = f"camp-rel-{uuid4().hex[:8]}"

    docs = [
        ("Pricing strategy for enterprise SaaS", _make_embedding(seed=10.0)),
        ("Cloud infrastructure monitoring guide", _make_embedding(seed=50.0)),
        ("Revenue operations best practices", _make_embedding(seed=90.0)),
    ]

    for content, emb in docs:
        await store_embedding(
            session=db_session,
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            content=content,
            embedding_vector=emb,
        )

    # Search with a vector close to the first document
    query_vector = _make_embedding(seed=10.1)  # Very close to seed=10.0
    results = await search_similar(
        session=db_session,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        query_vector=query_vector,
        top_k=3,
    )

    assert len(results) == 3
    # The first result should be the pricing doc (closest to seed=10.0)
    assert results[0].content == "Pricing strategy for enterprise SaaS"


# ---------------------------------------------------------------------------
# KnowledgeBaseLoader.load_all()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_all_knowledge_base(setup_tables, workspace_id):
    """Run KnowledgeBaseLoader.load_all(), verify entries stored in campaign_memory.

    This test uses the actual knowledge/ directory in the repo.
    The loader stores zero-vector placeholders (expected for v1).

    NOTE: load_all() and search_relevant() use the module-level
    async_session_factory from src.db.queries, which commits to the real DB.
    Unique workspace_id ensures isolation from other tests.
    """
    loader = KnowledgeBaseLoader()

    # Check that the KB root exists and has markdown files
    kb_root = loader.kb_root
    md_files = list(kb_root.rglob("*.md"))
    if not md_files:
        pytest.skip("No knowledge base markdown files found")

    count = await loader.load_all(
        workspace_id=workspace_id,
        campaign_id="knowledge_base",
    )

    assert count > 0, "Expected at least one KB entry to be stored"
    assert count == len(md_files), (
        f"Expected {len(md_files)} entries but stored {count}"
    )

    # Verify we can search (zero-vector returns all since distances are equal)
    results = await loader.search_relevant(
        query="pricing objection handling",
        workspace_id=workspace_id,
        campaign_id="knowledge_base",
        top_k=10,
    )

    assert len(results) > 0, "Should find KB entries after load_all()"
    # Each result should have the expected keys
    for r in results:
        assert "id" in r
        assert "content" in r
        assert len(r["content"]) > 0
