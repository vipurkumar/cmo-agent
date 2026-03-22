"""Shared FastAPI dependencies — importable without circular imports."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.queries import async_session_factory


async def get_session():
    """Yield an async DB session, committing on success / rolling back on error."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_workspace_id(
    request: Request,
    x_workspace_id: Annotated[str | None, Header()] = None,
) -> str:
    """Extract workspace_id — from API key auth (request.state) or X-Workspace-Id header."""
    # API key auth sets this
    ws_id = getattr(request.state, "workspace_id", None)
    if ws_id and ws_id != "__admin__":
        return ws_id
    # Fallback to header (for webhooks)
    if x_workspace_id:
        return x_workspace_id
    raise HTTPException(status_code=400, detail="Authentication required. Provide an API key or X-Workspace-Id header.")


async def get_pagination(page: int = 1, page_size: int = 20) -> dict[str, int]:
    """Extract pagination parameters with validation."""
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    return {"page": page, "page_size": page_size, "offset": (page - 1) * page_size}


# Dependency type aliases
SessionDep = Annotated[AsyncSession, Depends(get_session)]
WorkspaceDep = Annotated[str, Depends(get_workspace_id)]
PaginationDep = Annotated[dict[str, int], Depends(get_pagination)]
