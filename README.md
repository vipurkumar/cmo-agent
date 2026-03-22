# CMO Agent

**Multi-tenant AI agent platform for B2B GTM automation.**

CMO Agent runs AI-powered pipelines that automate go-to-market execution — outbound campaigns, account qualification, seller brief generation, and CRM writeback — for B2B companies at scale.

Built with LangGraph for agent orchestration, FastAPI for the API layer, and n8n for integrations. Targets 10,000+ concurrent sessions at < €0.08 LLM cost per session.

---

## Architecture

CMO Agent runs **two independent LangGraph pipelines**, each processing accounts through a sequence of specialized nodes:

### Outbound Pipeline

Executes multi-stage email campaigns with human-in-the-loop approval.

```
account_selector → researcher → personaliser → approval_gate → sender
                        ↑                                         ↓
                  enrichment_retry                          reply_monitor
                                                                ↓
                                                             router
                                                          ↙    ↓    ↘
                                                notify_sales  next   unsubscribe_handler
                                                          stage
                                                            ↓
                                                      memory_updater → next account or END
```

**Key capabilities:**
- Multi-stage email sequences with configurable delays
- Clay/Apollo enrichment with automatic retry
- LLM-powered personalization with scoring
- Slack-based approval gates
- Reply intent classification (positive/negative/neutral/unsubscribe)
- Campaign memory via pgvector for cross-session learning

### Qualification Pipeline (OmniGTM)

Scores accounts against your ICP, detects buying signals, and produces actionable seller briefs.

```
data_ingester → entity_resolver → [per-account loop]:
  icp_scorer → signal_detector → contact_ranker → pain_inferrer →
  value_prop_matcher → action_recommender → brief_builder →
  brief_reviewer → crm_writer → zoho_writer → task_creator →
  auto_outbound_gate → [next account or END]
```

**Key capabilities:**
- Deterministic ICP scoring (no LLM — pure rules for speed and consistency)
- Buying signal detection from news, web, job postings, and pricing pages
- Buying committee mapping with role classification
- LLM-powered pain hypothesis inference
- Value proposition matching to pain points
- Seller brief generation (8 structured sections)
- Human-in-the-loop brief approval or auto-approve
- CRM writeback (HubSpot + Zoho) and sales task creation
- Narrow auto-outbound for high-confidence cases with 6 guardrail checks

---

## Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.11+, uv |
| Agent Orchestration | LangGraph 0.2+, AsyncRedisSaver |
| LLM | Anthropic Claude (Sonnet for generation, Haiku for classification) |
| Embeddings | Voyage AI (voyage-3, 1024 dims) |
| API | FastAPI, Uvicorn, Pydantic v2 |
| Database | PostgreSQL 16 + pgvector |
| Cache & Locks | Redis 7 |
| Queue | BullMQ |
| Analytics | ClickHouse 24 |
| Connection Pooling | PgBouncer (NullPool on app side) |
| Integrations | n8n (webhooks) |
| Observability | Prometheus, Grafana, OpenTelemetry |
| Infra | Docker, Kubernetes, Helm |
| CI/CD | GitHub Actions |

---

## Quick Start

### Demo Mode (no external services)

```bash
# Install dependencies
uv sync --all-extras

# Run with mock tools — no API keys needed
CMO_DEMO_MODE=true uv run uvicorn src.api.main:app --reload
```

Open `http://localhost:8000/demo` for the interactive demo UI.

### Full Setup

```bash
# Install dependencies
uv sync --all-extras

# Start backing services
docker compose up -d
# PostgreSQL+pgvector on 5432, PgBouncer on 6432
# Redis on 6379, ClickHouse on 8123/9000

# Configure environment
cp .env.example .env
# Edit .env with your API keys (Anthropic, Apollo, etc.)

# Run database migrations
uv run prisma db push --schema=src/db/prisma/schema.prisma

# Start the API server
uv run uvicorn src.api.main:app --reload

# Start the worker (separate terminal)
uv run python -m src.worker.runner

# Create your first workspace (set CMO_ADMIN_API_KEY in .env first)
curl -X POST http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer YOUR_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Company", "plan": "pro"}'

# Use the returned API key for all subsequent requests
export CMO_API_KEY=cmo_returned_key_here
```

---

## Authentication

CMO Agent uses API keys for authentication. Every request (except health, docs, and webhooks) requires a valid API key.

### Getting Started

1. **Create a workspace** (requires admin API key):
```bash
curl -X POST http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer YOUR_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Company", "plan": "pro"}'
```

Response:
```json
{
  "workspace_id": "uuid-here",
  "name": "My Company",
  "plan": "pro",
  "api_key": "cmo_abc123..."
}
```

2. **Use the API key** on all subsequent requests:
```bash
curl http://localhost:8000/campaigns \
  -H "Authorization: Bearer cmo_abc123..."
```

3. **Create additional API keys**:
```bash
curl -X POST http://localhost:8000/api/v1/workspaces/{workspace_id}/api-keys \
  -H "Authorization: Bearer cmo_abc123..." \
  -H "Content-Type: application/json" \
  -d '{"name": "CI/CD Key"}'
```

### Plans & Rate Limits

| Plan | API Rate Limit | Apollo | Claude |
|------|---------------|--------|--------|
| Free | 60 req/min | 10 req/min | 15 req/min |
| Pro | 300 req/min | 100 req/min | 150 req/min |
| Enterprise | 1,000 req/min | 500 req/min | 600 req/min |

Rate limit headers are returned on every response:
- `X-RateLimit-Limit` — max requests per window
- `Retry-After` — seconds until rate limit resets (on 429)

### Error Responses

All errors follow a structured format:
```json
{
  "error_code": "AUTH_INVALID_KEY",
  "message": "Invalid or deactivated API key.",
  "request_id": "uuid-here"
}
```

Common error codes: `AUTH_MISSING_KEY`, `AUTH_INVALID_KEY`, `NOT_FOUND`, `RATE_LIMIT_EXCEEDED`, `VALIDATION_ERROR`, `INTERNAL_ERROR`.

---

## API Reference

### Campaigns

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/campaigns` | Create a new campaign |
| `GET` | `/campaigns` | List campaigns |
| `GET` | `/campaigns/{id}` | Get campaign details |
| `POST` | `/campaigns/{id}/trigger` | Trigger campaign execution |

### Qualification

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/campaigns/{id}/qualify` | Trigger batch qualification |
| `GET` | `/api/v1/accounts/{id}/brief` | Fetch seller brief |
| `POST` | `/api/v1/feedback` | Submit feedback on recommendations |

### Webhooks

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhooks/n8n` | n8n callback (approvals, replies) |
| `POST` | `/webhooks/approval` | Approval response |
| `POST` | `/webhooks/brief-approval` | Brief approval/rejection |

### Automation Control

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/automation/pause` | Pause automation for workspace |
| `POST` | `/api/v1/automation/resume` | Resume automation |
| `GET` | `/api/v1/automation/status` | Get automation status |
| `GET` | `/api/v1/automation/actions` | List recent automated actions |
| `POST` | `/api/v1/automation/actions/{brief_id}/review` | Flag action for review |

### CRM Embed

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/embed/{account_id}/card` | Compact HTML card for CRM sidebar |
| `GET` | `/embed/{account_id}/brief` | Full HTML seller brief |
| `GET` | `/embed/{account_id}/scores` | JSON scores for custom rendering |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin/ui` | Admin dashboard |
| `GET/PUT` | `/admin/config/icp` | ICP weights and criteria |
| `GET/PUT` | `/admin/config/thresholds` | Action thresholds |
| `GET/PUT` | `/admin/config/automation` | Automation config |
| `GET` | `/admin/stats` | Dashboard statistics |
| `GET` | `/admin/briefs/recent` | Recent briefs with scores |
| `GET` | `/admin/knowledge` | Knowledge base files |
| `POST` | `/admin/knowledge/reload` | Reload KB into pgvector |

### Other

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/evaluation/run` | Run evaluation metrics |
| `GET` | `/demo` | Demo UI (demo mode only) |
| `POST` | `/demo/run` | Run demo agent loop |
| `POST` | `/demo/qualify` | Run demo qualification |

### Knowledge Base

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/kb/upload` | Upload a KB entry (battlecard, case study, etc.) |
| `POST` | `/api/v1/kb/reload` | Reload static KB files into pgvector |
| `GET` | `/api/v1/kb/search?query=...` | Semantic search over knowledge base |

### Audit

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/audit/activity` | Recent workspace activity log |
| `GET` | `/api/v1/audit/summary` | High-level workspace summary |

### Export

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/export/briefs?format=json\|csv` | Export seller briefs |
| `GET` | `/api/v1/export/scores?format=json\|csv` | Export account scores |

### Usage

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/usage?days=30` | LLM usage and cost breakdown |

---

## Webhook Format

CMO Agent receives webhooks from n8n for approval responses and reply notifications.

### Authentication
All webhook requests must include an `X-Webhook-Signature` header with an HMAC-SHA256 signature of the request body using `CMO_HMAC_SECRET`.

```python
import hashlib, hmac
signature = hmac.new(HMAC_SECRET.encode(), body, hashlib.sha256).hexdigest()
```

### Payload Format

```json
{
  "event_type": "approval_response",
  "workspace_id": "ws-uuid",
  "payload": {
    "thread_id": "thread-uuid",
    "approved": true,
    "reviewer": "jane@acme.com"
  },
  "timestamp": "2026-03-22T10:00:00Z"
}
```

### Event Types

| Event Type | Queue | Description |
|------------|-------|-------------|
| `approval_response` | critical | Email draft approved/rejected |
| `positive_reply` | critical | Prospect replied positively |
| `unsubscribe_request` | critical | Unsubscribe request received |
| `brief_approval` | critical | Seller brief approved/rejected |
| `manual_trigger` | interactive | User-triggered campaign run |

---

## Scoring System

All scoring is **deterministic** (no LLM) for speed, cost, and auditability.

### ICP Fit Score (0–100)
Matches accounts against configurable criteria: industry, company size, revenue range, technology stack. Weighted scoring with evidence tracking.

### Pain Fit Score (0–100)
LLM-inferred pain hypotheses scored against known pain types (pricing complexity, quote-to-cash friction, billing mismatch, etc.). Each hypothesis backed by `Evidence` objects for traceability.

### Timing Score (0–100)
Signal recency and reliability scoring with configurable decay. Recent signals (funding, hiring, pricing changes) score higher.

### Action Decision
Pure-rules engine evaluates all three scores against thresholds:

| Action | Criteria |
|--------|----------|
| **Pursue Now** | Priority ≥ 60, contact relevance ≥ 70, pain confidence ≥ 0.50 |
| **Nurture** | Decent ICP fit but weak timing or pain signals |
| **Disqualify** | ICP fit below threshold or explicitly disqualified |
| **Human Review** | Low confidence or ambiguous evidence |

---

## Guardrails & Safety

### Kill Switch
- Global or per-workspace automation pause via Redis
- Auto-pause triggers on high error rate (>10%) or high negative reply rate (>25%)
- Configurable monitoring windows

### Send Caps
- Daily per-workspace: 25 (default)
- Weekly per-workspace: 100
- Daily per-account: 3
- 48-hour cooldown between messages to same contact

### Blocklist
- Domain, email, and company blocklists via Redis sets
- Auto-blocks unsubscribed contacts
- O(1) lookup on every send

### Auto-Outbound Thresholds
Automation requires **stricter** thresholds than manual action:
- Overall priority ≥ 80 (vs 60 for manual)
- Contact relevance ≥ 85 (vs 70)
- Pain confidence ≥ 0.70 (vs 0.50)
- Minimum 2 corroborating signals
- Maximum 3 unknowns in brief

---

## LLM Cost Control

All Claude API calls go through a single gateway (`src/llm/budget.py`) that enforces:

- **Per-task token budgets** (512–8192 tokens depending on task)
- **Model tiering** — Sonnet for generation, Haiku for classification
- **Cost logging** — every call logged to ClickHouse with workspace_id, task, tokens, cost
- **Cache control markers** — prompt templates use Anthropic's cache_control for reduced costs

| Task | Model | Max Tokens |
|------|-------|------------|
| Brief generation | Sonnet | 8,192 |
| Research | Sonnet | 8,192 |
| Email generation | Sonnet | 4,096 |
| Pain inference | Sonnet | 4,096 |
| Signal classification | Haiku | 512 |
| Reply analysis | Haiku | 1,024 |
| Title normalization | Haiku | 512 |

---

## Knowledge Base

The `/knowledge/` directory contains markdown files that are embedded into pgvector for semantic retrieval during brief generation:

- **Battlecards** — Competitive positioning against Zuora, Chargebee, Maxio, and build-in-house
- **Case Studies** — 6 customer success stories with metrics
- **Messaging** — Value propositions, objection handling, persona-specific angles, industry messaging

Reload via admin API: `POST /admin/knowledge/reload`

---

## Database Schema

### PostgreSQL (Transactional)

Core tables with mandatory `workspace_id` tenant isolation:

- `workspaces` / `workspace_settings` — tenant config
- `campaigns` / `sequences` — campaign definitions
- `accounts` / `contacts` / `messages` — GTM data
- `account_scores` / `signals` / `seller_brief_records` — qualification results
- `feedback_events` — user feedback on recommendations
- `campaign_memories` — pgvector embeddings for cross-session learning

### ClickHouse (Analytics)

Time-series event tables:

- `session_events` — session activity
- `cost_events` — LLM cost tracking
- `qualification_events` — scoring results over time
- `recommendation_events` — brief generation metrics
- `feedback_analytics` — feedback aggregation

---

## Queue System

Jobs are routed to priority-based queues:

| Queue | Concurrency | Use Case |
|-------|-------------|----------|
| `critical` | 10 | Approval responses, positive replies, unsubscribes |
| `interactive` | 5 | User-triggered actions, report requests |
| `batch` | 3 | Daily batches, qualification runs, reply checks |
| `background` | 2 | Memory updates, CRM syncs |

### Scheduled Jobs

| Job | Schedule | Purpose |
|-----|----------|---------|
| `daily_rescore` | 06:00 Mon–Fri | Re-score all accounts |
| `signal_refresh` | Every 4 hours | Refresh buying signals |
| `brief_refresh` | 08:00 Monday | Refresh seller briefs weekly |

---

## Testing

```bash
# Unit tests (fast, fully mocked)
uv run pytest tests/unit/ -v

# Single test file
uv run pytest tests/unit/test_guardrails.py -v

# Integration tests (requires backing services)
uv run pytest tests/integration/ -v

# Coverage report
uv run pytest --cov=src --cov-report=html

# Type checking
uv run mypy src/

# Linting
uv run ruff check src/
uv run ruff check src/ --fix  # auto-fix
```

---

## Deployment

### Docker

```bash
docker build -t cmo-agent .
docker run -p 8000:8000 --env-file .env cmo-agent
```

The Dockerfile runs as non-root user with a built-in health check.

### Kubernetes (Helm)

```bash
# Install with secrets
helm install omnigtm helm/omnigtm/ \
  --set secrets.CMO_ANTHROPIC_API_KEY=sk-ant-... \
  --set secrets.CMO_DATABASE_URL=postgresql+asyncpg://... \
  --set secrets.CMO_REDIS_URL=redis://...

# Or use a secrets override file
helm install omnigtm helm/omnigtm/ -f secrets-override.yaml
```

The Helm chart deploys:
- **API** — 2 replicas with liveness, readiness, and startup probes
- **Worker** — 1 replica with Redis connectivity health check
- **ServiceAccount** with RBAC
- **Security context** — runAsNonRoot, UID 1000

---

## Project Structure

```
src/
├── agent/           # LangGraph pipelines and nodes
├── api/             # FastAPI routes, middleware, schemas
├── admin/           # Admin dashboard and config API
├── db/              # PostgreSQL queries, pgvector, ClickHouse
├── llm/             # Claude API gateway, prompts, embeddings
├── tools/           # External API integrations (Apollo, Clay, HubSpot, etc.)
├── scoring/         # Deterministic ICP, timing, and action rules
├── normalization/   # Domain resolution, contact linking, title normalization
├── guardrails/      # Kill switch, send caps, blocklist
├── knowledge/       # KB loader for pgvector
├── evaluation/      # Precision/recall metrics and test accounts
├── worker/          # BullMQ workers, job handlers, scheduler
├── ratelimit/       # Redis-backed token bucket rate limiter
├── config/          # Settings, ICP defaults, automation thresholds
├── demo/            # Demo mode with mock tools and UI
└── logger.py        # Structured logging (structlog)
```

---

## Environment Variables

All variables use the `CMO_` prefix. See [`.env.example`](.env.example) for the full list.

**Required:**
- `CMO_ANTHROPIC_API_KEY` — Claude API key
- `CMO_DATABASE_URL` — PostgreSQL connection (via PgBouncer)
- `CMO_REDIS_URL` — Redis connection
- `CMO_HMAC_SECRET` — Webhook authentication
- `CMO_ADMIN_API_KEY` — Admin key for workspace provisioning

**Optional integrations:**
- `CMO_APOLLO_API_KEY` — Apollo.io enrichment
- `CMO_CLAY_API_KEY` — Clay enrichment
- `CMO_HUBSPOT_API_KEY` — HubSpot CRM
- `CMO_SLACK_BOT_TOKEN` — Slack approvals
- `CMO_ZOHO_CLIENT_ID/SECRET/REFRESH_TOKEN` — Zoho CRM

---

## License

Proprietary. All rights reserved.
