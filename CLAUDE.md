# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# CMO Agent — Claude Code Context

## Mission
CMO Agent is a multi-tenant SaaS that runs AI agents automating GTM execution
(outbound, content, SEO, social, lead nurture) for B2B companies at scale.
LangGraph handles agent reasoning. n8n handles integrations. FastAPI is the bridge.
Target: 10,000+ concurrent sessions with < €0.08 LLM cost per session.

---

## Stack (exact versions — always use these)

| Layer | Technology |
|---|---|
| Runtime | Python 3.11, uv for dependency management |
| Agent orchestration | LangGraph 0.2+, AsyncRedisSaver for checkpointing |
| LLM | Anthropic SDK 0.30+, claude-sonnet-4-6 (generation), claude-haiku-4-5-20251001 (classification) |
| Embeddings | Voyage AI (voyage-3, 1024 dims) via `src/llm/embeddings.py` |
| API server | FastAPI 0.115+, Uvicorn, Pydantic v2 |
| Database | PostgreSQL 16, SQLAlchemy 2.0 async (NullPool) |
| Cache + locks | Redis 7 + Sentinel |
| Queue | BullMQ (bullmq Python client) |
| Analytics | ClickHouse 24, clickhouse-driver |
| Vector memory | pgvector (inside PostgreSQL) |
| Connection pooling | PgBouncer (NullPool on app side) |
| Integrations | n8n self-hosted (separate service, talks via webhooks) |
| Observability | Prometheus, Grafana, OpenTelemetry, Loki |
| Infra | Kubernetes, Helm, GitHub Actions CI/CD |

---

## Architecture — Two LangGraph Pipelines

The system runs **two independent LangGraph StateGraphs**, each with its own state TypedDict:

### 1. Outbound Graph (`src/agent/graph.py` → `OutboundState`)
Campaign execution: account selection → research → personalization → approval → send → reply monitoring.
11 nodes for outbound email sequences.

### 2. Qualification Graph (`src/agent/qualification_graph.py` → `QualificationState`)
Account intelligence pipeline that produces a `SellerBrief` per account:
```
START → data_ingester → entity_resolver → [per-account loop]:
  icp_scorer → signal_detector → contact_ranker → pain_inferrer →
  value_prop_matcher → action_recommender → brief_builder →
  brief_reviewer → crm_writer → zoho_writer → task_creator →
  auto_outbound_gate → [next account or END]
```
Key routing:
- `_after_icp_scorer`: disqualified accounts skip to `action_recommender`
- `_after_brief_reviewer`: `pending_review` interrupts graph (waits for webhook)
- `_after_auto_outbound`: loops to next account or END

### Scoring Architecture (deterministic, no LLM)
- `src/scoring/icp_rules.py` — ICP fit scoring (industry, size, revenue matching)
- `src/scoring/timing_rules.py` — Signal freshness, recency decay, confidence
- `src/scoring/action_rules.py` — Thresholds for pursue_now / nurture / disqualify
- `src/config/action_thresholds.py` — Configurable threshold values

### Evidence Tracking
All scoring decisions are backed by `Evidence` objects (source, confidence, statement, evidence_type) for full traceability. Defined in `src/agent/state.py`.

---

## Architecture Rules — NEVER violate these

1. **LangGraph nodes are pure functions**: `(state: OutboundState | QualificationState) -> dict`.
   - No side effects inside nodes.
   - Side effects (DB writes, external API calls) happen ONLY inside Tool classes.
   - Return only the state keys you're updating: `return {"key": value}`

2. **ALL Claude API calls go through `src/llm/budget.py:call_claude()`**.
   - NEVER call `anthropic.messages.create()` directly anywhere in the codebase.
   - Budget enforcement, token counting, model tiering, and cost logging live in `budget.py`.

3. **ALL database writes go through `src/db/queries.py` typed functions**.
   - NEVER write raw SQL outside `queries.py`.
   - Use `src/db/campaign_memory.py` for all pgvector operations.

4. **Tenant isolation is mandatory on every query**.
   - Every DB query MUST include a `workspace_id` filter.
   - A query without `workspace_id` is a data leak bug, treated as P0.
   - Every Redis key MUST be prefixed: `{workspace_id}:{resource}:{id}`

5. **Rate limiting before every external API call**.
   - Call `RateLimiter.enforce(workspace_id, resource, plan)` BEFORE the HTTP call.
   - Defined in `src/ratelimit/bucket.py`.

6. **Distributed lock before every LangGraph thread resumption**.
   - Use `async with thread_lock(redis, thread_id)` from `src/worker/locks.py`.
   - Prevents race conditions when two webhooks resume the same thread.

7. **NullPool always — PgBouncer manages connections**.
   - `create_async_engine(..., poolclass=NullPool)`
   - NEVER set `pool_size` on the SQLAlchemy engine.

8. **Check guardrails before automation**.
   - `src/guardrails/kill_switch.py` — pause/resume automation globally or per-workspace
   - `src/guardrails/send_caps.py` — daily/weekly send caps per workspace (Redis-backed)
   - `src/guardrails/blocklist.py` — domain/company/contact blocklist enforcement

---

## File Structure — What Lives Where

```
src/
├── agent/
│   ├── state.py               ← OutboundState + QualificationState + ALL Pydantic models
│   ├── graph.py               ← Outbound LangGraph StateGraph (no business logic)
│   ├── qualification_graph.py ← Qualification LangGraph StateGraph (no business logic)
│   └── nodes/
│       ├── [outbound nodes]   ← account_selector, researcher, personaliser, approval_gate,
│       │                        sender, reply_monitor, router, memory_updater, notify_sales,
│       │                        enrichment_retry, unsubscribe_handler
│       └── [qualification nodes] ← data_ingester, entity_resolver, icp_scorer,
│                                   signal_detector, contact_ranker, pain_inferrer,
│                                   value_prop_matcher, action_recommender, brief_builder,
│                                   brief_reviewer, crm_writer, zoho_writer, task_creator,
│                                   auto_outbound_gate, brief_notifier, rollback_handler
├── tools/                     ← BaseTool subclasses (apollo_search, clay_enrich, news_search,
│                                linkedin_scraper, web_scraper, claude_writer, slack_approval,
│                                hubspot_tools, zoho_sync, crm_reader, job_posting_analyzer,
│                                pricing_page_analyzer, apollo_mcp)
├── scoring/                   ← Deterministic scoring rules (no LLM)
│   ├── icp_rules.py           ← ICP fit scoring
│   ├── timing_rules.py        ← Signal timing/recency scoring
│   └── action_rules.py        ← pursue_now / nurture / disqualify thresholds
├── normalization/             ← Data normalization
│   ├── domain_resolver.py     ← Domain canonicalization + alias resolution
│   ├── contact_linker.py      ← Contact deduplication + matching
│   └── title_normalizer.py    ← Job title → standard function/seniority
├── guardrails/                ← Automation safety controls
│   ├── send_caps.py           ← Daily/weekly send caps (Redis-backed)
│   ├── kill_switch.py         ← Pause/resume automation
│   └── blocklist.py           ← Domain/company/contact blocklist
├── knowledge/
│   └── loader.py              ← Loads markdown KB files → pgvector embeddings
├── api/
│   ├── main.py                ← FastAPI routes ONLY — no business logic
│   ├── middleware.py          ← HMAC auth, rate limiting middleware
│   ├── schemas.py             ← Request/response Pydantic models for API layer
│   ├── report.py              ← /report endpoint + ClickHouse queries
│   ├── deps.py                ← FastAPI dependency injection
│   ├── embed.py               ← CRM-embedded seller brief endpoints
│   └── embed_templates.py     ← HTML templates for CRM sidebar iframes
├── admin/
│   └── router.py              ← Admin API (ICP weights, thresholds, KB management)
├── evaluation/
│   └── metrics.py             ← Precision@k, recall, calibration metrics
├── db/
│   ├── prisma/schema.prisma
│   ├── queries.py             ← ALL typed DB query functions
│   ├── campaign_memory.py     ← pgvector read/write
│   └── clickhouse.py          ← ClickHouse analytics writes
├── llm/
│   ├── budget.py              ← ALL Claude API calls, token budgets, cost logging
│   ├── prompts.py             ← Prompt templates with cache_control markers
│   └── embeddings.py          ← Embedding provider (Voyage AI / OpenAI)
├── ratelimit/
│   └── bucket.py              ← Token bucket rate limiter (Redis Lua script)
├── worker/
│   ├── runner.py              ← BullMQ worker, session execution
│   ├── queues.py              ← Queue config, job routing, enqueue helper
│   ├── locks.py               ← Distributed thread locks
│   ├── scheduler.py           ← Scheduled jobs (daily_rescore, signal_refresh, brief_refresh)
│   └── handlers.py            ← Job handlers (qualification batch, etc.)
├── logger.py                  ← structlog logger (import as: from src.logger import log)
├── demo/                      ← Demo mode (CMO_DEMO_MODE=true, no external services)
└── config/
    ├── settings.py            ← Pydantic Settings — ALL env vars (CMO_ prefix)
    ├── icp.py                 ← Default ICP criteria + weights
    ├── action_thresholds.py   ← Action decision thresholds + confidence + decay
    └── automation.py          ← Automation config (caps, kill switch, rollback)
```

---

## Code Patterns — Copy These Exactly

### Adding a new LangGraph node

```python
# src/agent/nodes/my_new_node.py
from src.agent.state import OutboundState  # or QualificationState
from src.tools.some_tool import SomeTool
from src.logger import log

some_tool = SomeTool()

async def my_new_node(state: OutboundState) -> dict:
    log.info("my_new_node.start", thread_id=state["thread_id"],
             workspace_id=state["current_account"].workspace_id)

    result = await some_tool.run(
        input_data=state["some_field"],
        workspace_id=state["current_account"].workspace_id,
    )

    log.info("my_new_node.complete", thread_id=state["thread_id"])
    return {"some_output_field": result}  # return ONLY changed keys
```

### Adding a new tool

```python
# src/tools/my_tool.py
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.tools.base import BaseTool
from src.ratelimit.bucket import RateLimiter
from src.config import settings

class MyTool(BaseTool):
    def __init__(self, rate_limiter: RateLimiter):
        self.rate_limiter = rate_limiter

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.TransientError),
    )
    async def run(self, query: str, workspace_id: str, plan: str) -> MyResult:
        await self.rate_limiter.enforce(workspace_id, "my_api", plan)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.MY_API_BASE_URL}/endpoint",
                headers={"Authorization": f"Bearer {settings.MY_API_KEY}"},
                params={"q": query},
            )

        if resp.status_code == 429:
            raise MyApiRateLimitError(f"Rate limited by MyAPI for workspace {workspace_id}")
        if resp.status_code == 401:
            raise MyApiAuthError("Invalid MyAPI credentials")
        resp.raise_for_status()

        return MyResult(**resp.json())
```

### Calling Claude API

```python
# ALWAYS use this — NEVER call anthropic directly
from src.llm.budget import call_claude

result = await call_claude(
    task="email_generation",       # key in BUDGETS dict in budget.py
    system=system_prompt,
    user=user_prompt,
    workspace_id=workspace_id,
    model=settings.CLAUDE_MODEL,   # NEVER hardcode model name
)
```

### Database query

```python
# src/db/queries.py — add typed functions here
async def get_campaign(
    session: AsyncSession,
    campaign_id: str,
    workspace_id: str,             # ALWAYS include workspace_id
) -> Campaign | None:
    result = await session.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .where(Campaign.workspace_id == workspace_id)  # MANDATORY
    )
    return result.scalar_one_or_none()
```

### Enqueue a job

```python
from src.worker.queues import enqueue

job_id = await enqueue(
    queue_name="batch",            # critical / interactive / batch / background
    job_type="daily_batch",
    payload={"campaign_id": campaign_id},
    workspace_id=workspace_id,
)
```

---

## Queue Routing Reference

| event_type | Queue | Reason |
|---|---|---|
| `approval_response` | critical | Human is waiting |
| `positive_reply` | critical | AE needs to know now |
| `unsubscribe_request` | critical | Legal compliance |
| `brief_approval` | critical | Human reviewing seller brief |
| `manual_trigger` | interactive | User-initiated |
| `report_request` | interactive | User-initiated |
| `daily_batch` | batch | Scheduled, latency-tolerant |
| `check_replies` | batch | Scheduled |
| `qualification_batch` | batch | Account qualification pipeline |
| `memory_update` | background | Fire and forget |
| `crm_sync` | background | Fire and forget |

### Scheduled Jobs (src/worker/scheduler.py)

| Job | Cron | Purpose |
|---|---|---|
| `daily_rescore` | `0 6 * * 1-5` | Re-score all accounts daily |
| `signal_refresh` | `0 */4 * * *` | Refresh buying signals every 4 hours |
| `brief_refresh` | `0 8 * * 1` | Refresh seller briefs weekly |

---

## Key Settings (all in src/config/settings.py)

All env vars use the `CMO_` prefix (e.g. `CMO_CLAUDE_MODEL`, `CMO_DATABASE_URL`).
Copy `.env.example` to `.env` for local development.

```python
settings.CLAUDE_MODEL              # "claude-sonnet-4-6"
settings.CLAUDE_HAIKU_MODEL        # "claude-haiku-4-5-20251001"
settings.DATABASE_URL              # points to PgBouncer, NOT PostgreSQL directly
settings.REDIS_URL
settings.CLICKHOUSE_URL
settings.REDIS_KEY_PREFIX          # "cmo:" — prefix all Redis keys
settings.MAX_ACCOUNTS_PER_BATCH    # 20
settings.SEQUENCE_MAX_STAGES       # 3
settings.HMAC_SECRET               # for n8n webhook auth
settings.N8N_WEBHOOK_BASE_URL      # base URL for action webhooks
settings.EMBEDDING_PROVIDER        # "anthropic" (default)
settings.EMBEDDING_DIMENSIONS      # 1024
settings.USE_APOLLO_ENRICHMENT     # True
settings.APOLLO_MCP_ENABLED        # False
```

---

## Local Development Setup

```bash
# Install dependencies
uv sync --all-extras

# Start backing services (PostgreSQL+pgvector, PgBouncer, Redis, ClickHouse)
docker compose up -d

# PgBouncer is on port 6432, PostgreSQL direct on 5432
# Redis on 6379, ClickHouse HTTP on 8123 / native on 9000

# Run database migrations
uv run prisma db push --schema=src/db/prisma/schema.prisma

# Run the API server
uv run uvicorn src.api.main:app --reload

# Run in demo mode (no external services required)
CMO_DEMO_MODE=true uv run uvicorn src.api.main:app --reload
```

---

## How to Run Tests

```bash
# Unit tests (fast, fully mocked, no network)
uv run pytest tests/unit/ -v

# Single test file or specific test
uv run pytest tests/unit/test_tools.py -v
uv run pytest tests/unit/test_tools.py::test_specific_name -v

# Integration tests (requires .env.test with real API keys)
uv run pytest tests/integration/ -v
uv run pytest tests/integration/ -v -m apollo    # Apollo-only
uv run pytest tests/integration/ -v -m clay      # Clay-only

# Coverage report
uv run pytest --cov=src --cov-report=html

# Type checking
uv run mypy src/

# Linting
uv run ruff check src/

# Auto-fix lint issues
uv run ruff check src/ --fix
```

---

## Common Mistakes — Claude Code Must Avoid

- **Direct anthropic calls**: `anthropic.messages.create()` — use `call_claude()` instead
- **Sync SQLAlchemy**: `session.execute()` without `await` — we are async-only
- **Missing workspace_id in queries**: any DB query without tenant filter is a bug
- **`os.environ.get()`**: use `from src.config import settings` instead
- **`print()` for logging**: use `from src.logger import log` with structlog
- **New Pydantic models in tool files**: all models live in `src/agent/state.py`
- **Hardcoded model names**: always use `settings.CLAUDE_MODEL`
- **Direct PostgreSQL connection string**: DATABASE_URL always points to PgBouncer
- **Opening DB connections in tool files**: use dependency injection from FastAPI
- **Calling tools directly inside nodes**: tools are called through LangGraph's ToolNode
- **State mutation**: nodes return new dict, never mutate state in place
- **Skipping guardrails before automation**: always check kill_switch, send_caps, blocklist
- **Using OutboundState for qualification nodes**: use `QualificationState` instead
- **Calling scoring rules directly without the action gate**: route through `action_recommender`

---

## Prompt Templates for Common Tasks

### New Tool
```
Implement src/tools/{TOOL_NAME}.py for CMO Agent.
- Calls {API_NAME} to {PURPOSE}
- Input: {PYDANTIC_INPUT_MODEL} (already in state.py — import from there)
- Output: {PYDANTIC_OUTPUT_MODEL}
- Follow the pattern in src/tools/apollo_search.py exactly
- Rate limit resource name: "{RESOURCE_NAME}"
- Include tests/unit/test_{tool_name}.py with respx mocks for 200, 401, 429
```

### New Node
```
Implement src/agent/nodes/{NODE_NAME}.py for CMO Agent.
- Reads {INPUT_KEYS} from OutboundState (or QualificationState)
- Calls {TOOL_NAMES} (already implemented — import from src/tools/)
- Returns dict with only these keys updated: {OUTPUT_KEYS}
- Follow the pattern in src/agent/nodes/researcher.py (outbound)
  or src/agent/nodes/icp_scorer.py (qualification)
- Include tests/unit/test_{node_name}.py with AsyncMock for all tools
```

### New API Endpoint
```
Add {METHOD} /{path} to src/api/main.py.
- Request schema: add {RequestModel} to src/api/schemas.py
- Response schema: add {ResponseModel} to src/api/schemas.py
- Business logic: add function to src/db/queries.py or src/worker/queues.py
- Add HMAC auth via the existing middleware
- Include unit test in tests/unit/test_api.py using FastAPI TestClient
```

---

## API Route Groups

- **Campaign CRUD**: `POST /api/v1/campaigns`, `GET /api/v1/campaigns/{id}`
- **Qualification**: `POST /api/v1/campaigns/{id}/qualify`, `GET /api/v1/accounts/{id}/brief`
- **Feedback**: `POST /api/v1/feedback`
- **Webhooks**: `POST /webhooks/n8n`, `POST /webhooks/brief-approval`
- **Automation control**: `POST /api/v1/automation/pause|resume`, `GET /api/v1/automation/status|actions`
- **Evaluation**: `POST /api/v1/evaluation/run`
- **CRM embed**: `GET /embed/{account_id}/card|full|json`
- **Admin**: via `src/admin/router.py` (ICP weights, thresholds, KB)
- **Reports**: `GET /api/v1/report`
- **Demo**: `POST /demo/qualify`, `POST /demo/run`

---

## gstack — AI Engineering Skills

gstack is installed at `.claude/skills/gstack/` and provides slash-command skills for structured development workflows.

**Web browsing**: ALWAYS use `/browse` from gstack for all web browsing tasks. NEVER use `mcp__claude-in-chrome__*` tools.

**Available skills**:
- `/office-hours` — product reframing and design docs
- `/plan-ceo-review` — CEO-level plan review
- `/plan-eng-review` — engineering plan review and test planning
- `/plan-design-review` — design plan review
- `/design-consultation` — design consultation
- `/review` — staff engineer code review
- `/ship` — tests, coverage, PR creation
- `/browse` — headless Chromium browser (use this for ALL web browsing)
- `/qa` — real browser testing + bug fixing
- `/qa-only` — browser testing, report only
- `/design-review` — design review
- `/setup-browser-cookies` — configure browser cookies
- `/retro` — weekly retrospective
- `/investigate` — root-cause debugging
- `/document-release` — auto-update docs after release
- `/codex` — second opinion from OpenAI Codex CLI
- `/careful` — enable extra caution mode
- `/freeze` — freeze changes
- `/guard` — guard mode
- `/unfreeze` — unfreeze changes
- `/gstack-upgrade` — upgrade gstack

**Troubleshooting**: If gstack skills aren't working, run `cd .claude/skills/gstack && ./setup` to rebuild the binaries and re-register skills.

---

## Session Checklist — Start of Every Claude Code Session

Before writing any code, Claude Code should:
1. Determine which graph the feature belongs to (outbound or qualification)
2. Check which queue the new feature belongs to (critical/interactive/batch/background)
3. Confirm workspace_id flows through every function that touches data
4. Confirm all Claude API calls go through budget.py
5. Confirm the new file has a corresponding test file
6. Confirm any new Pydantic models belong in state.py, not in the new file
7. For automation features: confirm guardrails (kill_switch, send_caps, blocklist) are checked
