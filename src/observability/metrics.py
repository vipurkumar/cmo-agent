"""Prometheus metrics for CMO Agent.

All metrics use workspace_id as a label for multi-tenant visibility.
Import and use these counters/histograms throughout the codebase.
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# ---------------------------------------------------------------------------
# App info
# ---------------------------------------------------------------------------
APP_INFO = Info("cmo_agent", "CMO Agent application info")
APP_INFO.info({"version": "0.3.0", "service": "cmo-agent"})

# ---------------------------------------------------------------------------
# HTTP request metrics
# ---------------------------------------------------------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "cmo_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION = Histogram(
    "cmo_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ---------------------------------------------------------------------------
# LLM / Claude metrics
# ---------------------------------------------------------------------------
LLM_CALLS_TOTAL = Counter(
    "cmo_llm_calls_total",
    "Total LLM API calls",
    ["task", "model", "workspace_id"],
)

LLM_TOKENS_TOTAL = Counter(
    "cmo_llm_tokens_total",
    "Total LLM tokens consumed",
    ["direction", "model", "workspace_id"],  # direction: input/output
)

LLM_COST_USD = Counter(
    "cmo_llm_cost_usd_total",
    "Total LLM cost in USD",
    ["task", "model", "workspace_id"],
)

LLM_CALL_DURATION = Histogram(
    "cmo_llm_call_duration_seconds",
    "LLM call duration in seconds",
    ["task", "model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# ---------------------------------------------------------------------------
# Job / worker metrics
# ---------------------------------------------------------------------------
JOBS_TOTAL = Counter(
    "cmo_jobs_total",
    "Total jobs processed",
    ["job_type", "queue", "status"],  # status: complete/failed
)

JOB_DURATION = Histogram(
    "cmo_job_duration_seconds",
    "Job processing duration in seconds",
    ["job_type", "queue"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

JOBS_IN_PROGRESS = Gauge(
    "cmo_jobs_in_progress",
    "Number of jobs currently being processed",
    ["queue"],
)

# ---------------------------------------------------------------------------
# Qualification pipeline metrics
# ---------------------------------------------------------------------------
ACCOUNTS_SCORED = Counter(
    "cmo_accounts_scored_total",
    "Total accounts scored",
    ["action", "workspace_id"],  # action: pursue_now/nurture/disqualify/human_review
)

BRIEFS_GENERATED = Counter(
    "cmo_briefs_generated_total",
    "Total seller briefs generated",
    ["workspace_id"],
)

# ---------------------------------------------------------------------------
# Rate limiting metrics
# ---------------------------------------------------------------------------
RATE_LIMIT_HITS = Counter(
    "cmo_rate_limit_hits_total",
    "Total rate limit rejections",
    ["resource", "workspace_id"],
)

# ---------------------------------------------------------------------------
# Guardrail metrics
# ---------------------------------------------------------------------------
SEND_CAP_HITS = Counter(
    "cmo_send_cap_hits_total",
    "Total send cap rejections",
    ["cap_type", "workspace_id"],
)

AUTOMATION_PAUSES = Counter(
    "cmo_automation_pauses_total",
    "Total automation pause events",
    ["reason_type", "workspace_id"],
)

# ---------------------------------------------------------------------------
# API key auth metrics
# ---------------------------------------------------------------------------
AUTH_FAILURES = Counter(
    "cmo_auth_failures_total",
    "Total authentication failures",
    ["reason"],  # missing_key, invalid_key, deactivated
)
