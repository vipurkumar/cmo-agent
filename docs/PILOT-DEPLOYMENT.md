# CMO Agent — First Customer Pilot Deployment Guide

## Overview

This guide walks you through deploying CMO Agent for your first customer to test
the **qualification pipeline** (account scoring → seller briefs). No outbound
email sends, no CRM integration needed.

## What the Customer Gets

| Feature | Status |
|---|---|
| Web dashboard (login, campaigns, accounts, briefs) | Ready |
| Account qualification (ICP scoring, pain inference) | Ready |
| Seller brief generation & viewing | Ready |
| Knowledge base management | Ready |
| Team management (invite users, roles) | Ready |
| Webhook notifications | Ready |
| CRM integration | Not needed for pilot |
| Outbound email sends | Not needed for pilot |

---

## Prerequisites

- A server (VPS, cloud VM, or local machine) with:
  - Docker & Docker Compose
  - Python 3.11+ and `uv`
  - Node.js 18+ (for frontend build)
  - 4GB+ RAM, 2 CPU cores
- An **Anthropic API key** (for Claude — the LLM powering qualification)
- A domain name + HTTPS (recommended for customer-facing deployment)

---

## Step 1: Clone & Configure

```bash
git clone <your-repo-url> cmo-agent
cd cmo-agent
cp .env.example .env
```

Edit `.env` and set these **required** values:

```bash
# REQUIRED — LLM for qualification
CMO_ANTHROPIC_API_KEY=sk-ant-your-key-here

# REQUIRED — admin secret for workspace provisioning
CMO_ADMIN_API_KEY=generate-a-strong-random-string

# REQUIRED — webhook security
CMO_HMAC_SECRET=generate-another-strong-random-string
```

Everything else can stay at defaults for pilot.

**You do NOT need** Apollo, Clay, Slack, HubSpot, Zoho, or n8n keys for
qualification-only testing.

---

## Step 2: Start Services & Deploy

```bash
# Option A: Use the deployment script
chmod +x scripts/deploy-pilot.sh
./scripts/deploy-pilot.sh

# Option B: Manual steps
docker compose up -d                                     # backing services
uv sync --all-extras                                     # Python dependencies
uv run prisma db push --schema=src/db/prisma/schema.prisma  # DB schema
cd frontend && npm ci && npm run build && cd ..          # frontend
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000  # API server
```

In a separate terminal, start the background worker:

```bash
uv run python -m src.worker.runner
```

---

## Step 3: Set Up HTTPS (Production)

For customer-facing deployment, put a reverse proxy in front:

```bash
# Using Caddy (simplest — auto HTTPS)
caddy reverse-proxy --from yourdomain.com --to localhost:8000

# Or using Nginx
# See standard Nginx reverse proxy config for port 8000
```

Update `.env`:
```bash
CMO_CORS_ALLOWED_ORIGINS=["https://yourdomain.com"]
```

---

## Step 4: Customer Onboarding

Send the customer this link: `https://yourdomain.com/app/login`

### Customer walkthrough:

1. **Create Account** — Click "Create Account", enter email + password + company name
   - This creates their workspace and first user automatically

2. **Upload Knowledge Base** (optional but improves quality)
   - Go to **Knowledge Base** tab
   - Upload battlecards, case studies, messaging docs
   - These improve pain inference and value prop matching

3. **Create a Campaign**
   - Go to **Campaigns** tab → "New Campaign"
   - Enter campaign name
   - Set ICP criteria: target industries, employee range

4. **Run Qualification**
   - Click "Qualify" on the campaign
   - System runs: data ingestion → ICP scoring → signal detection → pain inference → seller brief generation

5. **Review Results**
   - Go to **Accounts & Briefs** tab
   - See scored accounts with priority ratings
   - Click "View Brief" for full seller brief (why this account, why now, talk tracks, risks)
   - Filter by: Pursue Now / Nurture / Disqualify

6. **Manage Settings**
   - **Settings** tab: API keys, team members, webhooks, automation controls

---

## What to Expect

### Qualification Pipeline Flow
```
Campaign Created → ICP Scoring → Signal Detection → Contact Ranking →
Pain Inference → Value Prop Matching → Action Recommendation →
Seller Brief Generation → Brief Review → Results Available
```

### Scoring Output (per account)
- **ICP Fit** (0-100): How well the account matches target criteria
- **Pain Fit** (0-100): How strong the inferred pain points are
- **Timing** (0-100): How urgent/timely the signals are
- **Overall Priority** (0-100): Weighted composite score
- **Action**: Pursue Now / Nurture / Disqualify

### Seller Brief Contains
- Account snapshot (company, size, industry)
- Why this account (ICP fit reasons)
- Why now (buying signals, timing)
- Key contacts (ranked by relevance)
- Pain hypotheses (with evidence)
- Talk tracks (personalized messaging)
- Risks and unknowns

---

## Monitoring

- **Application logs**: stdout from uvicorn process
- **Grafana dashboards**: `http://yourdomain.com:3000` (admin/admin)
- **API health**: `GET /health` — checks DB, Redis, ClickHouse connectivity
- **Prometheus metrics**: `GET /metrics`

---

## Troubleshooting

| Issue | Fix |
|---|---|
| "Dashboard not built" at /app | Run `cd frontend && npm run build` |
| Qualification hangs | Check worker is running: `uv run python -m src.worker.runner` |
| 500 errors on API | Check `.env` has valid `CMO_ANTHROPIC_API_KEY` |
| DB connection errors | Verify docker services: `docker compose ps` |
| Scores all zero | Upload knowledge base content for better scoring |

---

## Costs

- **LLM cost**: ~€0.03-0.08 per account qualification (Claude Sonnet)
- **Infrastructure**: Minimal — runs on a single 4GB VPS (~€5-20/month)
- **External APIs**: None required for qualification-only pilot

---

## Next Steps After Pilot

Once the customer validates qualification quality:

1. **Add Apollo enrichment** — Set `CMO_APOLLO_API_KEY` for real company data
2. **Connect CRM** — HubSpot or Zoho integration for auto-writeback
3. **Enable outbound** — n8n + Slack for email campaign execution
4. **Scale** — Deploy to Kubernetes with Helm chart (`helm/omnigtm/`)
