"""CRM-embeddable endpoints for OmniGTM seller briefs.

Serves lightweight HTML widgets designed to be embedded in HubSpot
or Zoho CRM sidebar iframes. Also serves JSON API for custom integrations.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.deps import SessionDep, WorkspaceDep
from src.api.embed_templates import render_card, render_full_brief, render_no_data
from src.db.queries import get_account_score, get_seller_brief
from src.logger import log

router = APIRouter(prefix="/embed", tags=["embed"])


@router.get("/{account_id}/card", response_class=HTMLResponse)
async def embed_card(
    account_id: str,
    session: SessionDep,
    workspace_id: WorkspaceDep,
    theme: str = Query("light", pattern="^(light|dark)$"),
) -> HTMLResponse:
    """Return a compact HTML card for CRM sidebar iframe embedding.

    Fits a 300px-wide sidebar. Shows overall score, action badge,
    top contact, top pain, and one-line hook.
    """
    log.info("embed.card", workspace_id=workspace_id, account_id=account_id)

    brief = await get_seller_brief(
        session=session, account_id=account_id, workspace_id=workspace_id
    )
    if not brief:
        return HTMLResponse(content=render_no_data(account_id))

    score = await get_account_score(
        session=session, account_id=account_id, workspace_id=workspace_id
    )

    brief_data = {
        "account_id": brief.account_id,
        "brief_json": brief.brief_json,
        "action_type": brief.action_type,
        "overall_score": brief.overall_score,
        "confidence_score": brief.confidence_score,
        "version": brief.version,
        "generated_at": str(brief.generated_at) if brief.generated_at else "",
    }

    score_data = {}
    if score:
        score_data = {
            "overall_priority_score": score.overall_priority_score,
            "icp_fit_score": score.icp_fit_score,
            "pain_fit_score": score.pain_fit_score,
            "timing_score": score.timing_score,
            "confidence_score": score.confidence_score,
        }

    html = render_card(brief_data, score_data, theme=theme)
    return HTMLResponse(content=html)


@router.get("/{account_id}/brief", response_class=HTMLResponse)
async def embed_brief(
    account_id: str,
    session: SessionDep,
    workspace_id: WorkspaceDep,
) -> HTMLResponse:
    """Return a full HTML seller brief for popup/modal display.

    Renders all 8 brief sections with score gauges, contact cards,
    and signal badges. Print-friendly, standalone page.
    """
    log.info("embed.brief", workspace_id=workspace_id, account_id=account_id)

    brief = await get_seller_brief(
        session=session, account_id=account_id, workspace_id=workspace_id
    )
    if not brief:
        return HTMLResponse(content=render_no_data(account_id))

    score = await get_account_score(
        session=session, account_id=account_id, workspace_id=workspace_id
    )

    brief_data = {
        "account_id": brief.account_id,
        "brief_json": brief.brief_json,
        "action_type": brief.action_type,
        "overall_score": brief.overall_score,
        "confidence_score": brief.confidence_score,
        "version": brief.version,
        "generated_at": str(brief.generated_at) if brief.generated_at else "",
    }

    score_data = {}
    if score:
        score_data = {
            "overall_priority_score": score.overall_priority_score,
            "icp_fit_score": score.icp_fit_score,
            "pain_fit_score": score.pain_fit_score,
            "timing_score": score.timing_score,
            "confidence_score": score.confidence_score,
        }

    html = render_full_brief(brief_data, score_data)
    return HTMLResponse(content=html)


@router.get("/{account_id}/scores")
async def embed_scores(
    account_id: str,
    session: SessionDep,
    workspace_id: WorkspaceDep,
) -> JSONResponse:
    """Return JSON scores for CRM custom card rendering.

    Simple flat JSON designed for HubSpot/Zoho custom cards
    that render their own UI.
    """
    log.info("embed.scores", workspace_id=workspace_id, account_id=account_id)

    brief = await get_seller_brief(
        session=session, account_id=account_id, workspace_id=workspace_id
    )
    score = await get_account_score(
        session=session, account_id=account_id, workspace_id=workspace_id
    )

    if not brief and not score:
        return JSONResponse(
            status_code=404,
            content={"detail": "No qualification data for this account"},
        )

    brief_json = (brief.brief_json or {}) if brief else {}

    # Extract top contact name
    contacts = brief_json.get("recommended_contacts", [])
    top_contact_name = contacts[0].get("name", "") if contacts else ""

    # Extract top pain type
    pains = brief_json.get("likely_pain_points", [])
    top_pain_type = pains[0].get("pain_type", "") if pains else ""

    result = {
        "overall_score": score.overall_priority_score if score else (brief.overall_score if brief else 0),
        "icp_fit": score.icp_fit_score if score else 0,
        "pain_fit": score.pain_fit_score if score else 0,
        "timing": score.timing_score if score else 0,
        "action": brief.action_type if brief else "unknown",
        "confidence": score.confidence_score if score else (brief.confidence_score if brief else 0.0),
        "top_contact_name": top_contact_name,
        "top_pain_type": top_pain_type,
    }

    return JSONResponse(content=result)


@router.get("/{account_id}/json", tags=["embed"])
async def embed_json(
    account_id: str,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Return the seller brief as JSON for custom CRM rendering."""
    brief = await get_seller_brief(session=session, account_id=account_id, workspace_id=workspace_id)
    if not brief:
        raise HTTPException(status_code=404, detail="No brief found for this account")

    score = await get_account_score(session=session, account_id=account_id, workspace_id=workspace_id)

    return {
        "brief_id": brief.id,
        "account_id": brief.account_id,
        "version": brief.version,
        "action_type": brief.action_type,
        "overall_score": brief.overall_score,
        "confidence_score": brief.confidence_score,
        "brief": brief.brief_json,
        "scoring": {
            "icp_fit": score.icp_fit_score if score else None,
            "pain_fit": score.pain_fit_score if score else None,
            "timing": score.timing_score if score else None,
            "overall_priority": score.overall_priority_score if score else None,
            "confidence": score.confidence_score if score else None,
        },
        "generated_at": str(brief.generated_at) if brief.generated_at else None,
    }
