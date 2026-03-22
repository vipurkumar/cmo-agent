"""Customer dashboard — serves the React SPA.

In development: Run `npm run dev` in frontend/ (port 3001 with proxy to 8000).
In production: Serves the built files from frontend/dist/.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from starlette.staticfiles import StaticFiles

router = APIRouter(tags=["dashboard"])

_frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"


# Serve static assets (JS, CSS, images) from the build output
if _frontend_dist.exists():
    router.mount("/app/assets", StaticFiles(directory=_frontend_dist / "assets"), name="static-assets")


@router.get("/app/{path:path}", include_in_schema=False)
async def serve_spa(path: str = ""):
    """Serve the React SPA. All routes return index.html for client-side routing."""
    index = _frontend_dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse(
        content="<h1>Dashboard not built</h1>"
        "<p>Run <code>cd frontend && npm run build</code> to build the React app.</p>",
        status_code=200,
    )
