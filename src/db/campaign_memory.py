"""pgvector operations for campaign memory.

Stores and retrieves embedding vectors used for semantic search over
campaign context (past emails, research notes, account intel, etc.).
"""

from __future__ import annotations

from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.db.queries import Base
from src.logger import log

# ---------------------------------------------------------------------------
# DB vector column dimension — fixed at 1536 for backward compatibility.
# If the embedding model produces fewer dimensions (e.g. voyage-3 = 1024),
# vectors are padded with zeros by src.llm.embeddings before storage.
# ---------------------------------------------------------------------------
EMBEDDING_DIM = 1536


class CampaignMemory(Base):
    __tablename__ = "campaign_memory"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Query functions — workspace_id is MANDATORY on every query
# ---------------------------------------------------------------------------


async def store_embedding(
    session: AsyncSession,
    workspace_id: str,
    campaign_id: str,
    content: str,
    embedding_vector: list[float],
) -> CampaignMemory:
    """Store a content chunk with its embedding vector."""
    log.info(
        "campaign_memory.store_embedding",
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        content_length=len(content),
    )
    memory = CampaignMemory(
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        content=content,
        embedding=embedding_vector,
    )
    session.add(memory)
    await session.flush()
    return memory


async def search_similar(
    session: AsyncSession,
    workspace_id: str,
    campaign_id: str,
    query_vector: list[float],
    top_k: int = 5,
) -> list[CampaignMemory]:
    """Find the top-k most similar memories by cosine distance.

    Uses pgvector's <=> (cosine distance) operator for ordering.
    Results are scoped to the given workspace and campaign.
    """
    log.debug(
        "campaign_memory.search_similar",
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        top_k=top_k,
    )
    # Use pgvector cosine distance operator (<=>)
    stmt = (
        select(CampaignMemory)
        .where(CampaignMemory.workspace_id == workspace_id)
        .where(CampaignMemory.campaign_id == campaign_id)
        .order_by(CampaignMemory.embedding.cosine_distance(query_vector))
        .limit(top_k)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
