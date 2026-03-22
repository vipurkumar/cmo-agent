"""FastAPI routes — NO business logic. Delegates to queries.py and queues.py."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse as StarletteJSONResponse

from src.api.deps import SessionDep, WorkspaceDep
from src.api.middleware import ApiKeyAuthMiddleware, HMACAuthMiddleware, RateLimitMiddleware, RequestIdMiddleware, WorkspaceExtractor
from src.api.schemas import (
    ApprovalResponse,
    AutomationPauseRequest,
    AutomationStatusResponse,
    BriefGenerateRequest,
    CampaignDetailResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    CreateCampaignRequest,
    CreateCampaignResponse,
    CreateWorkspaceRequest,
    CreateWorkspaceResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    QualifyBatchRequest,
    QualifyBatchResponse,
    SellerBriefResponse,
    WebhookPayload,
)
from src.db.queries import (
    async_session_factory,
    create_api_key,
    create_campaign,
    create_workspace,
    deactivate_api_key,
    get_campaign,
    get_seller_brief,
    get_workspace,
    list_campaigns,
    save_feedback_event,
)
from src.config import settings
from src.logger import log
from src.worker.queues import enqueue, enqueue_by_event

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CMO Agent API",
    version="0.1.0",
    description="AI-powered GTM execution platform for B2B companies.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "workspaces", "description": "Workspace and API key management"},
        {"name": "campaigns", "description": "Campaign management"},
        {"name": "qualification", "description": "Account qualification and scoring"},
        {"name": "automation", "description": "Automation control"},
        {"name": "embed", "description": "CRM-embeddable endpoints"},
        {"name": "export", "description": "Data export (JSON/CSV)"},
        {"name": "usage", "description": "Usage and cost tracking"},
        {"name": "webhooks", "description": "Webhook receivers"},
        {"name": "admin", "description": "Configuration and admin"},
    ],
)

# CORS — permissive for feedback release, tighten for GA
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"],
)

# Middleware — order matters: outermost first
app.add_middleware(WorkspaceExtractor)
app.add_middleware(RateLimitMiddleware, requests_per_minute=60)
app.add_middleware(ApiKeyAuthMiddleware)
app.add_middleware(HMACAuthMiddleware)
app.add_middleware(RequestIdMiddleware)

# Include sub-routers
from src.admin.router import router as admin_router  # noqa: E402
from src.api.report import router as report_router  # noqa: E402

app.include_router(admin_router)
app.include_router(report_router)

from src.api.embed import router as embed_router  # noqa: E402
from src.api.export import router as export_router  # noqa: E402

app.include_router(embed_router)
app.include_router(export_router)

from src.api.kb import router as kb_router  # noqa: E402
from src.api.audit import router as audit_router  # noqa: E402

app.include_router(kb_router)
app.include_router(audit_router)

from src.api.notifications import router as notifications_router  # noqa: E402

app.include_router(notifications_router)


# ---------------------------------------------------------------------------
# Structured error handlers
# ---------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return structured error responses for all HTTP exceptions."""
    error_codes = {
        400: "BAD_REQUEST",
        401: "AUTH_REQUIRED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
    }
    request_id = getattr(request.state, "request_id", None)
    return StarletteJSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": error_codes.get(exc.status_code, "ERROR"),
            "message": exc.detail,
            "request_id": request_id,
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return structured validation errors with field details."""
    request_id = getattr(request.state, "request_id", None)
    return StarletteJSONResponse(
        status_code=422,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {"errors": exc.errors()},
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — no stack trace in response."""
    request_id = getattr(request.state, "request_id", None)
    log.exception("unhandled_error", request_id=request_id, path=request.url.path)
    return StarletteJSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
            "request_id": request_id,
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health(request: Request):
    """Health check — verifies DB, Redis, and ClickHouse connectivity."""
    import asyncio

    from redis.asyncio import Redis as AsyncRedis

    services: dict[str, str] = {}
    status = "ok"

    # Check PostgreSQL via PgBouncer
    try:
        async with async_session_factory() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        services["database"] = "ok"
    except Exception as exc:
        services["database"] = f"down: {type(exc).__name__}"
        status = "degraded"

    # Check Redis
    try:
        redis = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await redis.ping()
            services["redis"] = "ok"
        finally:
            await redis.aclose()
    except Exception as exc:
        services["redis"] = f"down: {type(exc).__name__}"
        status = "degraded"

    # Check ClickHouse (best-effort, non-critical)
    try:
        from clickhouse_driver import Client as SyncCH
        ch = SyncCH.from_url(settings.CLICKHOUSE_URL)
        await asyncio.to_thread(ch.execute, "SELECT 1")
        services["clickhouse"] = "ok"
    except Exception:
        services["clickhouse"] = "unavailable"

    http_status = 200 if services.get("database") == "ok" and services.get("redis") == "ok" else 503
    return StarletteJSONResponse(
        status_code=http_status,
        content={
            "status": status,
            "version": "0.1.0",
            "timestamp": datetime.now(UTC).isoformat(),
            "services": services,
        },
    )


@app.post("/api/v1/workspaces", status_code=201, tags=["workspaces"])
async def create_workspace_route(
    body: CreateWorkspaceRequest,
    session: SessionDep,
):
    """Create a new workspace and its first API key. Requires admin API key."""
    workspace = await create_workspace(session=session, name=body.name, plan=body.plan)
    api_key_record, raw_key = await create_api_key(session=session, workspace_id=workspace.id)
    return CreateWorkspaceResponse(
        workspace_id=workspace.id,
        name=workspace.name,
        plan=workspace.plan,
        api_key=raw_key,
    )


@app.post("/api/v1/workspaces/{workspace_id}/api-keys", status_code=201, tags=["workspaces"])
async def create_api_key_route(
    workspace_id: str,
    body: CreateApiKeyRequest,
    session: SessionDep,
    ws_id: WorkspaceDep,
):
    """Create an additional API key for a workspace."""
    if ws_id != workspace_id:
        raise HTTPException(status_code=403, detail="Cannot create keys for other workspaces")
    workspace = await get_workspace(session=session, workspace_id=workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    api_key_record, raw_key = await create_api_key(session=session, workspace_id=workspace_id, name=body.name)
    return CreateApiKeyResponse(
        key_id=api_key_record.id,
        api_key=raw_key,
        name=api_key_record.name,
    )


@app.delete("/api/v1/workspaces/{workspace_id}/api-keys/{key_id}", tags=["workspaces"])
async def delete_api_key_route(
    workspace_id: str,
    key_id: str,
    session: SessionDep,
    ws_id: WorkspaceDep,
):
    """Deactivate an API key."""
    if ws_id != workspace_id:
        raise HTTPException(status_code=403, detail="Cannot manage keys for other workspaces")
    success = await deactivate_api_key(session=session, key_id=key_id, workspace_id=workspace_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "deactivated"}


@app.post("/campaigns", response_model=CreateCampaignResponse, status_code=201, tags=["campaigns"])
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


@app.get("/campaigns", tags=["campaigns"])
async def list_campaigns_route(
    session: SessionDep,
    workspace_id: WorkspaceDep,
    page: int = 1,
    page_size: int = 20,
):
    """List campaigns for the workspace with pagination."""
    log.info("api.list_campaigns", workspace_id=workspace_id)
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size
    campaigns, total = await list_campaigns(
        session=session, workspace_id=workspace_id, offset=offset, limit=page_size
    )
    import math
    return {
        "items": [
            {
                "id": c.id,
                "name": c.name,
                "status": "draft",
                "created_at": c.created_at,
            }
            for c in campaigns
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 0,
    }


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
