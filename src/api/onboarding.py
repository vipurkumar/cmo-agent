"""Customer onboarding UI and API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["onboarding"])

_onboarding_html = Path(__file__).parent / "onboarding_ui.html"


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page():
    """Serve the customer onboarding page."""
    return HTMLResponse(content=_onboarding_html.read_text())
