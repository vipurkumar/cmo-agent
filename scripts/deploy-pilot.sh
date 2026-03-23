#!/usr/bin/env bash
# deploy-pilot.sh — Deploy CMO Agent for first customer pilot testing
# Usage: ./scripts/deploy-pilot.sh
set -euo pipefail

echo "=== CMO Agent — Pilot Deployment ==="
echo ""

# ─── 1. Check prerequisites ───
echo "1. Checking prerequisites..."
for cmd in docker uv node; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: $cmd is not installed."
    exit 1
  fi
done
echo "   All prerequisites found."

# ─── 2. Environment setup ───
if [ ! -f .env ]; then
  echo ""
  echo "2. Creating .env from .env.example..."
  cp .env.example .env
  echo "   IMPORTANT: Edit .env and set at minimum:"
  echo "   - CMO_ANTHROPIC_API_KEY  (required for qualification)"
  echo "   - CMO_ADMIN_API_KEY      (set a strong random secret)"
  echo "   - CMO_HMAC_SECRET        (set a strong random secret)"
  echo ""
  echo "   For qualification-only (no outbound), you do NOT need:"
  echo "   - Slack, HubSpot, Zoho, n8n credentials"
  echo ""
  read -p "   Edit .env now and press Enter to continue..."
else
  echo "2. .env already exists — using existing config."
fi

# ─── 3. Start backing services ───
echo ""
echo "3. Starting backing services (PostgreSQL, PgBouncer, Redis, ClickHouse)..."
docker compose up -d
echo "   Waiting for services to be healthy..."
sleep 5

# Check health
docker compose ps --format "table {{.Name}}\t{{.Status}}" | head -10

# ─── 4. Install Python dependencies ───
echo ""
echo "4. Installing Python dependencies..."
uv sync --all-extras 2>&1 | tail -3

# ─── 5. Run database migrations ───
echo ""
echo "5. Running database migrations..."
uv run prisma db push --schema=src/db/prisma/schema.prisma 2>&1 | tail -5

# ─── 6. Build frontend ───
echo ""
echo "6. Building frontend dashboard..."
cd frontend
npm ci --silent 2>&1 | tail -3
npm run build 2>&1 | tail -5
cd ..
echo "   Frontend built to frontend/dist/"

# ─── 7. Load knowledge base ───
echo ""
echo "7. Loading knowledge base into vector store..."
echo "   (This will happen on first API call or via /api/v1/kb/reload)"

# ─── 8. Start the API server ───
echo ""
echo "============================================"
echo "  DEPLOYMENT COMPLETE"
echo "============================================"
echo ""
echo "  Start the API server:"
echo "    uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "  Start the worker (separate terminal):"
echo "    uv run python -m src.worker.runner"
echo ""
echo "  Then open:"
echo "    Dashboard:   http://YOUR_SERVER:8000/app"
echo "    Onboarding:  http://YOUR_SERVER:8000/onboarding"
echo "    API Docs:    http://YOUR_SERVER:8000/docs"
echo "    Grafana:     http://YOUR_SERVER:3000 (admin/admin)"
echo ""
echo "  Customer first steps:"
echo "    1. Open http://YOUR_SERVER:8000/app/login"
echo "    2. Click 'Create Account' (registers workspace + user)"
echo "    3. Go to Campaigns → Create a campaign with ICP criteria"
echo "    4. Click 'Qualify' on the campaign"
echo "    5. View results in Accounts & Briefs page"
echo ""
echo "  For HTTPS (production), put Nginx/Caddy in front:"
echo "    caddy reverse-proxy --from yourdomain.com --to localhost:8000"
echo ""
