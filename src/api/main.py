"""FastAPI routes — NO business logic. Delegates to queries.py and queues.py."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request

from src.api.deps import SessionDep, WorkspaceDep
from src.api.middleware import HMACAuthMiddleware, RateLimitMiddleware, WorkspaceExtractor
from src.api.schemas import (
    ApprovalResponse,
    AutomationPauseRequest,
    AutomationStatusResponse,
    BriefGenerateRequest,
    CampaignDetailResponse,
    CreateCampaignRequest,
    CreateCampaignResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    QualifyBatchRequest,
    QualifyBatchResponse,
    SellerBriefResponse,
    WebhookPayload,
)
from src.db.queries import (
    create_campaign,
    get_campaign,
    get_seller_brief,
    list_campaigns,
    save_feedback_event,
)
from src.config import settings
from src.logger import log
from src.worker.queues import enqueue, enqueue_by_event

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(title="CMO Agent API", version="0.1.0")

# Middleware — order matters: outermost first
app.add_middleware(WorkspaceExtractor)
app.add_middleware(RateLimitMiddleware, requests_per_minute=60)
app.add_middleware(HMACAuthMiddleware)

# Include sub-routers
from src.admin.router import router as admin_router  # noqa: E402
from src.api.report import router as report_router  # noqa: E402

app.include_router(admin_router)
app.include_router(report_router)

from src.api.embed import router as embed_router  # noqa: E402

app.include_router(embed_router)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        timestamp=datetime.now(UTC),
    )


@app.post("/campaigns", response_model=CreateCampaignResponse, status_code=201)
async def create_campaign_route(
    body: CreateCampaignRequest,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Create a new campaign for the workspace."""
    log.info("api.create_campaign", workspace_id=workspace_id, name=body.name)
    campaign = await create_campaign(
        session=session,
        workspace_id=workspace_id,
        name=body.name,
        icp_criteria=body.icp_criteria,
        sequence_config=body.sequence_config,
    )
    return CreateCampaignResponse(
        id=campaign.id,
        name=campaign.name,
        status="draft",
        created_at=campaign.created_at,
    )


@app.get("/campaigns", response_model=list[CreateCampaignResponse])
async def list_campaigns_route(
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """List all campaigns for the workspace."""
    log.info("api.list_campaigns", workspace_id=workspace_id)
    campaigns = await list_campaigns(session=session, workspace_id=workspace_id)
    return [
        CreateCampaignResponse(
            id=c.id,
            name=c.name,
            status="draft",
            created_at=c.created_at,
        )
        for c in campaigns
    ]


@app.get("/campaigns/{campaign_id}", response_model=CampaignDetailResponse)
async def get_campaign_route(
    campaign_id: str,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Get detailed info for a single campaign."""
    log.info("api.get_campaign", workspace_id=workspace_id, campaign_id=campaign_id)
    campaign = await get_campaign(
        session=session, campaign_id=campaign_id, workspace_id=workspace_id
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignDetailResponse(
        id=campaign.id,
        name=campaign.name,
        status="draft",
        icp_criteria=campaign.icp_criteria,
        sequence_config=campaign.sequence_config,
        created_at=campaign.created_at,
    )


@app.post("/campaigns/{campaign_id}/trigger", status_code=202)
async def trigger_campaign_route(
    campaign_id: str,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Trigger campaign execution by enqueuing a job."""
    log.info("api.trigger_campaign", workspace_id=workspace_id, campaign_id=campaign_id)

    # Verify the campaign exists and belongs to this workspace
    campaign = await get_campaign(
        session=session, campaign_id=campaign_id, workspace_id=workspace_id
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    job_id = await enqueue(
        queue_name="interactive",
        job_type="manual_trigger",
        payload={"campaign_id": campaign_id},
        workspace_id=workspace_id,
    )
    return {"job_id": job_id, "status": "enqueued"}


@app.post("/webhooks/n8n", status_code=200)
async def n8n_webhook(body: WebhookPayload):
    """Receive n8n callbacks (approval responses, replies, etc.).

    HMAC signature is validated by HMACAuthMiddleware.
    Routes the event to the correct queue based on event_type.
    """
    log.info(
        "api.n8n_webhook",
        event_type=body.event_type,
        workspace_id=body.workspace_id,
    )
    job_id = await enqueue_by_event(
        event_type=body.event_type,
        payload=body.payload,
        workspace_id=body.workspace_id,
    )
    return {"job_id": job_id, "status": "accepted"}


@app.post("/webhooks/approval", status_code=200)
async def approval_webhook(body: ApprovalResponse, request: Request):
    """Receive approval responses from Slack / reviewers.

    HMAC signature is validated by HMACAuthMiddleware.
    """
    workspace_id = getattr(request.state, "workspace_id", None)
    if not workspace_id:
        raise HTTPException(status_code=400, detail="X-Workspace-Id header is required")

    log.info(
        "api.approval_webhook",
        thread_id=body.thread_id,
        approved=body.approved,
        reviewer=body.reviewer,
        workspace_id=workspace_id,
    )
    job_id = await enqueue_by_event(
        event_type="approval_response",
        payload={
            "thread_id": body.thread_id,
            "approved": body.approved,
            "reviewer": body.reviewer,
        },
        workspace_id=workspace_id,
    )
    return {"job_id": job_id, "status": "accepted"}


# ---------------------------------------------------------------------------
# OmniGTM Qualification endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/campaigns/{campaign_id}/qualify", status_code=202)
async def qualify_batch_route(
    campaign_id: str,
    body: QualifyBatchRequest,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Trigger batch qualification for accounts in a campaign."""
    log.info("api.qualify_batch", workspace_id=workspace_id, campaign_id=campaign_id)

    campaign = await get_campaign(
        session=session, campaign_id=campaign_id, workspace_id=workspace_id
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    job_id = await enqueue(
        queue_name="batch",
        job_type="qualification_batch",
        payload={
            "campaign_id": campaign_id,
            "account_ids": body.account_ids,
            "max_accounts": body.max_accounts,
        },
        workspace_id=workspace_id,
    )
    return QualifyBatchResponse(
        job_id=job_id,
        queue="batch",
        accounts_queued=len(body.account_ids) or body.max_accounts,
    )


@app.get("/api/v1/accounts/{account_id}/brief")
async def get_brief_route(
    account_id: str,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Fetch the latest seller brief for an account."""
    log.info("api.get_brief", workspace_id=workspace_id, account_id=account_id)

    brief = await get_seller_brief(
        session=session, account_id=account_id, workspace_id=workspace_id
    )
    if not brief:
        raise HTTPException(status_code=404, detail="No brief found for this account")

    return {
        "brief_id": brief.id,
        "account_id": brief.account_id,
        "version": brief.version,
        "action_type": brief.action_type,
        "overall_score": brief.overall_score,
        "confidence_score": brief.confidence_score,
        "brief": brief.brief_json,
        "generated_at": brief.generated_at,
    }


@app.post("/api/v1/feedback", status_code=201)
async def feedback_route(
    body: FeedbackRequest,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Capture feedback on a recommendation."""
    log.info(
        "api.feedback",
        workspace_id=workspace_id,
        recommendation_id=body.recommendation_id,
    )
    record = await save_feedback_event(
        session=session,
        workspace_id=workspace_id,
        recommendation_id=body.recommendation_id,
        recommendation_type=body.recommendation_type,
        user_id=body.user_id,
        action_taken=body.action_taken,
        correction=body.correction,
    )
    return FeedbackResponse(
        feedback_id=record.id,
        recorded_at=record.created_at,
    )


@app.post("/webhooks/brief-approval", status_code=200)
async def brief_approval_webhook(body: ApprovalResponse, request: Request):
    """Receive brief approval/rejection from Slack reviewers."""
    workspace_id = getattr(request.state, "workspace_id", None)
    if not workspace_id:
        raise HTTPException(status_code=400, detail="X-Workspace-Id header is required")

    log.info(
        "api.brief_approval",
        thread_id=body.thread_id,
        approved=body.approved,
        reviewer=body.reviewer,
        workspace_id=workspace_id,
    )
    job_id = await enqueue_by_event(
        event_type="brief_approval",
        payload={
            "thread_id": body.thread_id,
            "approved": body.approved,
            "reviewer": body.reviewer,
        },
        workspace_id=workspace_id,
    )
    return {"job_id": job_id, "status": "accepted"}


# ---------------------------------------------------------------------------
# Automation control endpoints
# ---------------------------------------------------------------------------

from redis.asyncio import Redis as AsyncRedis

from src.agent.nodes.rollback_handler import (
    get_automation_status,
    list_recent_auto_actions,
    mark_for_review,
    pause_automation,
    resume_automation,
)


def _get_redis() -> AsyncRedis:
    """Return a shared async Redis client for automation endpoints."""
    return AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)


@app.post("/api/v1/automation/pause", status_code=200)
async def pause_automation_route(
    body: AutomationPauseRequest,
    workspace_id: WorkspaceDep,
):
    """Pause automation for a workspace."""
    log.info("api.pause_automation", workspace_id=workspace_id, reason=body.reason)
    redis_client = _get_redis()
    try:
        result = await pause_automation(redis_client, workspace_id, body.reason)
    finally:
        await redis_client.aclose()
    return result


@app.post("/api/v1/automation/resume", status_code=200)
async def resume_automation_route(
    workspace_id: WorkspaceDep,
):
    """Resume automation for a workspace."""
    log.info("api.resume_automation", workspace_id=workspace_id)
    redis_client = _get_redis()
    try:
        result = await resume_automation(redis_client, workspace_id)
    finally:
        await redis_client.aclose()
    return result


@app.get("/api/v1/automation/status", response_model=AutomationStatusResponse)
async def automation_status_route(
    workspace_id: WorkspaceDep,
):
    """Get automation status for a workspace."""
    log.info("api.automation_status", workspace_id=workspace_id)
    redis_client = _get_redis()
    try:
        result = await get_automation_status(redis_client, workspace_id)
    finally:
        await redis_client.aclose()
    return AutomationStatusResponse(**result)


@app.get("/api/v1/automation/actions")
async def list_auto_actions_route(
    session: SessionDep,
    workspace_id: WorkspaceDep,
    limit: int = 50,
):
    """List recent automated outbound actions."""
    log.info("api.list_auto_actions", workspace_id=workspace_id)
    return await list_recent_auto_actions(session, workspace_id, limit=limit)


@app.post("/api/v1/automation/actions/{brief_id}/review", status_code=200)
async def mark_for_review_route(
    brief_id: str,
    session: SessionDep,
    workspace_id: WorkspaceDep,
    reviewer: str = "system",
):
    """Mark an automated action for human review."""
    log.info(
        "api.mark_for_review",
        workspace_id=workspace_id,
        brief_id=brief_id,
        reviewer=reviewer,
    )
    return await mark_for_review(session, brief_id, workspace_id, reviewer)


# ---------------------------------------------------------------------------
# Evaluation endpoint
# ---------------------------------------------------------------------------


@app.post("/api/v1/evaluation/run")
async def run_evaluation_route(workspace_id: WorkspaceDep):
    """Run evaluation against test accounts and return metrics."""
    from src.evaluation.evaluator import run_evaluation
    from src.evaluation.test_accounts import TEST_ACCOUNTS

    log.info("api.run_evaluation", workspace_id=workspace_id)
    report = await run_evaluation(TEST_ACCOUNTS, workspace_id)
    return report.to_dict()


# ---------------------------------------------------------------------------
# Demo endpoint — only registered when CMO_DEMO_MODE=true
# ---------------------------------------------------------------------------

if settings.DEMO_MODE:
    from pathlib import Path

    from fastapi.responses import HTMLResponse

    from src.demo.bootstrap import build_demo_graph, create_demo_state, init_demo

    _demo_html_path = Path(__file__).parent.parent / "demo" / "ui.html"

    @app.get("/demo", response_class=HTMLResponse)
    async def demo_ui():
        """Serve the single-page demo UI."""
        return HTMLResponse(content=_demo_html_path.read_text())

    @app.on_event("startup")
    async def _setup_demo():
        init_demo()
        try:
            from src.demo.bootstrap import init_demo_qualification
            init_demo_qualification()
        except Exception:
            pass  # qualification demo is optional

    @app.post("/demo/run")
    async def run_demo():
        """Run the full agent loop with mock data — no external deps needed."""
        graph = build_demo_graph()
        state = create_demo_state()
        config = {"configurable": {"thread_id": state["thread_id"]}}

        steps: list[dict] = []
        async for event in graph.astream(state, config=config):
            for node_name, node_output in event.items():
                if node_name == "__end__":
                    continue
                step: dict = {"node": node_name}
                if node_output:
                    for key, val in node_output.items():
                        if hasattr(val, "model_dump"):
                            step[key] = val.model_dump()
                        elif isinstance(val, list) and val and hasattr(val[0], "model_dump"):
                            step[key] = [v.model_dump() for v in val]
                        else:
                            step[key] = val
                steps.append(step)

        return {"status": "complete", "steps": steps, "total_nodes_executed": len(steps)}

    @app.post("/demo/qualify")
    async def run_demo_qualification():
        """Run the OmniGTM qualification pipeline with demo data — no external deps."""
        from src.demo.bootstrap import (
            build_demo_qualification_graph,
            create_demo_qualification_state,
            init_demo_qualification,
        )

        init_demo_qualification()
        graph = build_demo_qualification_graph()
        state = create_demo_qualification_state()
        config = {"configurable": {"thread_id": state["thread_id"]}}

        steps: list[dict] = []
        async for event in graph.astream(state, config=config):
            for node_name, node_output in event.items():
                if node_name == "__end__":
                    continue
                step: dict = {"node": node_name}
                if node_output:
                    for key, val in node_output.items():
                        if hasattr(val, "model_dump"):
                            step[key] = val.model_dump(mode="json")
                        elif isinstance(val, list) and val and hasattr(val[0], "model_dump"):
                            step[key] = [v.model_dump(mode="json") for v in val]
                        else:
                            step[key] = val
                steps.append(step)

        return {"status": "complete", "steps": steps, "total_nodes_executed": len(steps)}
