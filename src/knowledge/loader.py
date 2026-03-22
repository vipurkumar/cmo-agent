"""KnowledgeBaseLoader — loads markdown KB files and stores embeddings in pgvector.

Uses real embeddings via src.llm.embeddings (Voyage AI or OpenAI).
Falls back to zero vectors if the embedding provider is unavailable.
"""

from __future__ import annotations

from pathlib import Path

from src.db.campaign_memory import store_embedding, search_similar, CampaignMemory
from src.db.queries import async_session_factory
from src.llm.embeddings import embed_text
from src.logger import log

# Root directory for knowledge base files
KB_ROOT = Path(__file__).resolve().parent.parent.parent / "knowledge"


class KnowledgeBaseLoader:
    """Loads knowledge base markdown files into pgvector for semantic search.

    Usage::

        loader = KnowledgeBaseLoader()
        await loader.load_all(workspace_id="ws_123")
        results = await loader.search_relevant(
            query="pricing objection",
            workspace_id="ws_123",
            campaign_id="camp_456",
        )
    """

    def __init__(self, kb_root: Path | None = None) -> None:
        self.kb_root = kb_root or KB_ROOT

    async def load_all(self, workspace_id: str, campaign_id: str = "knowledge_base") -> int:
        """Load all markdown files from the knowledge directory and store in pgvector.

        Parameters
        ----------
        workspace_id:
            Tenant identifier — mandatory for every DB write.
        campaign_id:
            Campaign ID to associate entries with. Defaults to ``"knowledge_base"``.

        Returns
        -------
        int
            Number of KB entries stored.
        """
        log.info(
            "knowledge_loader.load_all.start",
            workspace_id=workspace_id,
            kb_root=str(self.kb_root),
        )

        md_files = sorted(self.kb_root.rglob("*.md"))
        if not md_files:
            log.warn(
                "knowledge_loader.load_all.no_files",
                workspace_id=workspace_id,
                kb_root=str(self.kb_root),
            )
            return 0

        count = 0
        async with async_session_factory() as session, session.begin():
            for md_file in md_files:
                content = md_file.read_text(encoding="utf-8").strip()
                if not content:
                    continue

                # Prefix content with file path for context
                relative_path = md_file.relative_to(self.kb_root)
                tagged_content = f"[source: {relative_path}]\n\n{content}"

                # Generate real embedding for the KB content
                embedding_vector = await embed_text(tagged_content, input_type="document")

                await store_embedding(
                    session=session,
                    workspace_id=workspace_id,
                    campaign_id=campaign_id,
                    content=tagged_content,
                    embedding_vector=embedding_vector,
                )
                count += 1

                log.info(
                    "knowledge_loader.stored",
                    workspace_id=workspace_id,
                    file=str(relative_path),
                    content_length=len(tagged_content),
                )

        log.info(
            "knowledge_loader.load_all.complete",
            workspace_id=workspace_id,
            entries_stored=count,
        )
        return count

    async def search_relevant(
        self,
        query: str,
        workspace_id: str,
        campaign_id: str = "knowledge_base",
        top_k: int = 5,
    ) -> list[dict[str, str]]:
        """Search pgvector for relevant KB entries.

        Parameters
        ----------
        query:
            The search query text.
        workspace_id:
            Tenant identifier — mandatory for every DB query.
        campaign_id:
            Campaign ID scope. Defaults to ``"knowledge_base"``.
        top_k:
            Maximum number of results to return.

        Returns
        -------
        list[dict[str, str]]
            List of dicts with ``id``, ``content``, and ``created_at`` keys.
        """
        log.info(
            "knowledge_loader.search.start",
            workspace_id=workspace_id,
            query=query[:100],
            top_k=top_k,
        )

        # Embed the query with the same model used for storage
        query_vector = await embed_text(query, input_type="query")

        async with async_session_factory() as session:
            memories: list[CampaignMemory] = await search_similar(
                session=session,
                workspace_id=workspace_id,
                campaign_id=campaign_id,
                query_vector=query_vector,
                top_k=top_k,
            )

        results = [
            {
                "id": mem.id,
                "content": mem.content,
                "created_at": str(mem.created_at) if mem.created_at else "",
            }
            for mem in memories
        ]

        log.info(
            "knowledge_loader.search.complete",
            workspace_id=workspace_id,
            result_count=len(results),
        )
        return results
