"""Shared FastAPI dependencies — importable without circular imports."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException
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
    x_workspace_id: Annotated[str | None, Header()] = None,
) -> str:
    """Extract workspace_id from X-Workspace-Id header (required)."""
    if not x_workspace_id:
        raise HTTPException(status_code=400, detail="X-Workspace-Id header is required")
    return x_workspace_id


# Dependency type aliases
SessionDep = Annotated[AsyncSession, Depends(get_session)]
WorkspaceDep = Annotated[str, Depends(get_workspace_id)]
