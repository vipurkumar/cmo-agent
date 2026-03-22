"""Customer dashboard — serves the SPA and page JS modules at /app."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from starlette.responses import Response

router = APIRouter(tags=["dashboard"])

_dashboard_path = Path(__file__).parent / "dashboard.html"
_pages_dir = Path(__file__).parent / "pages"


@router.get("/app/pages/{filename}", include_in_schema=False)
async def serve_page_js(filename: str):
    """Serve page JS modules for the dashboard."""
    if not filename.endswith(".js"):
        raise HTTPException(status_code=404)
    filepath = _pages_dir / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404)
    return Response(
        content=filepath.read_text(),
        media_type="application/javascript",
    )


@router.get("/app", response_class=HTMLResponse)
@router.get("/app/{path:path}", response_class=HTMLResponse)
async def dashboard(path: str = ""):
    """Serve the customer dashboard SPA."""
    return HTMLResponse(content=_dashboard_path.read_text())
