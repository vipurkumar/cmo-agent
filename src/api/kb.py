"""Knowledge base management API — upload, list, delete KB entries."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException
from pydantic import BaseModel

from src.api.deps import WorkspaceDep
from src.knowledge.loader import KnowledgeBaseLoader
from src.db.campaign_memory import store_embedding
from src.db.queries import async_session_factory
from src.llm.embeddings import embed_text
from src.logger import log

router = APIRouter(prefix="/api/v1/kb", tags=["knowledge-base"])


class KBEntryResponse(BaseModel):
    id: str
    title: str
    kb_type: str
    content_preview: str
    workspace_id: str


class KBUploadResponse(BaseModel):
    entries_stored: int
    message: str


@router.post("/upload", response_model=KBUploadResponse)
async def upload_kb_entry(
    workspace_id: WorkspaceDep,
    title: str = Form(...),
    kb_type: str = Form(..., description="Type: battlecard, case_study, messaging, objection_handling"),
    content: str = Form(..., description="Markdown content"),
):
    """Upload a knowledge base entry and store its embedding in pgvector."""
    log.info("api.kb_upload", workspace_id=workspace_id, title=title, kb_type=kb_type)

    if kb_type not in ("battlecard", "case_study", "messaging", "objection_handling"):
        raise HTTPException(status_code=400, detail=f"Invalid kb_type: {kb_type}. Must be one of: battlecard, case_study, messaging, objection_handling")

    if len(content) < 10:
        raise HTTPException(status_code=400, detail="Content too short (minimum 10 characters)")

    if len(content) > 50000:
        raise HTTPException(status_code=400, detail="Content too long (maximum 50,000 characters)")

    # Generate embedding
    try:
        embedding = await embed_text(content[:8000])  # Truncate for embedding
    except Exception as exc:
        log.warning("api.kb_upload.embedding_failed", error=str(exc))
        embedding = [0.0] * 1024  # Fallback zero vector

    # Store in pgvector
    try:
        async with async_session_factory() as session:
            await store_embedding(
                session=session,
                workspace_id=workspace_id,
                campaign_id=f"kb:{kb_type}",
                content=f"# {title}\n\n{content}",
                embedding_vector=embedding,
            )
            await session.commit()
    except Exception as exc:
        log.error("api.kb_upload.store_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to store KB entry")

    return KBUploadResponse(entries_stored=1, message=f"Successfully stored '{title}' as {kb_type}")


@router.post("/reload", status_code=202)
async def reload_knowledge_base(workspace_id: WorkspaceDep):
    """Reload all static KB files from the knowledge/ directory into pgvector."""
    log.info("api.kb_reload", workspace_id=workspace_id)
    try:
        loader = KnowledgeBaseLoader()
        count = await loader.load_all(workspace_id=workspace_id)
        return {"status": "completed", "entries_loaded": count}
    except Exception as exc:
        log.error("api.kb_reload.failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"KB reload failed: {exc}")


@router.get("/search")
async def search_kb(
    workspace_id: WorkspaceDep,
    query: str = "",
    limit: int = 5,
):
    """Search the knowledge base using semantic similarity."""
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter is required")

    log.info("api.kb_search", workspace_id=workspace_id, query=query[:50])
    try:
        loader = KnowledgeBaseLoader()
        results = await loader.search_relevant(
            query=query,
            workspace_id=workspace_id,
            campaign_id="knowledge_base",
            top_k=limit,
        )
        return {"results": results, "query": query, "count": len(results)}
    except Exception as exc:
        log.error("api.kb_search.failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Search failed")
