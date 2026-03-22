"""Central LLM gateway — ALL Claude API calls go through call_claude().

NEVER call anthropic.messages.create() outside of this module.
"""

from __future__ import annotations

import time

import anthropic

from src.config import settings
from src.logger import log
from src.observability.metrics import LLM_CALLS_TOTAL, LLM_TOKENS_TOTAL, LLM_COST_USD, LLM_CALL_DURATION

# ---------------------------------------------------------------------------
# Token budgets per task (max_tokens sent to the API)
# ---------------------------------------------------------------------------
BUDGETS: dict[str, int] = {
    "email_generation": 4096,
    "classification": 512,
    "research": 8192,
    "personalization": 2048,
    "summarization": 1024,
    "reply_analysis": 1024,
    "title_normalization": 512,
    "signal_classification": 512,
    "pain_inference": 4096,
    "contact_ranking": 2048,
    "value_prop_matching": 4096,
    "brief_generation": 8192,
    "account_pain_scoring": 2048,
}

# ---------------------------------------------------------------------------
# Per-token costs (USD) — update when Anthropic changes pricing
# ---------------------------------------------------------------------------
MODEL_COSTS: dict[str, dict[str, float]] = {
    "sonnet": {
        "input": 3.00 / 1_000_000,   # $3.00 per 1M input tokens
        "output": 15.00 / 1_000_000,  # $15.00 per 1M output tokens
    },
    "haiku": {
        "input": 0.80 / 1_000_000,   # $0.80 per 1M input tokens
        "output": 4.00 / 1_000_000,   # $4.00 per 1M output tokens
    },
}

# Singleton async client — reused across calls
_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def _model_family(model: str) -> str:
    """Return the cost-table key ('sonnet' or 'haiku') for a model string."""
    if "haiku" in model:
        return "haiku"
    return "sonnet"


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Return the estimated USD cost for a single API call."""
    family = _model_family(model)
    costs = MODEL_COSTS[family]
    return (input_tokens * costs["input"]) + (output_tokens * costs["output"])


async def call_claude(
    task: str,
    system: str | list[dict],
    user: str,
    workspace_id: str,
    model: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """Single entry-point for every Claude API call in the codebase.

    Parameters
    ----------
    task:
        Key in ``BUDGETS`` — used to enforce default token limits.
    system:
        System prompt (plain string or Anthropic content-block list with
        cache_control markers).
    user:
        User/human prompt text.
    workspace_id:
        Tenant identifier — logged for cost attribution.
    model:
        Override model name.  Defaults to ``settings.CLAUDE_MODEL``.
    max_tokens:
        Override token budget.  Falls back to ``BUDGETS[task]``.
    """
    resolved_model = model or settings.CLAUDE_MODEL
    resolved_max_tokens = max_tokens or BUDGETS.get(task, 1024)

    log.info(
        "llm.call.start",
        task=task,
        model=resolved_model,
        max_tokens=resolved_max_tokens,
        workspace_id=workspace_id,
    )

    client = _get_client()

    _call_start = time.monotonic()
    response = await client.messages.create(
        model=resolved_model,
        max_tokens=resolved_max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    _call_duration = time.monotonic() - _call_start

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = calculate_cost(resolved_model, input_tokens, output_tokens)

    log.info(
        "llm.call.complete",
        task=task,
        model=resolved_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost, 6),
        workspace_id=workspace_id,
    )

    # Prometheus metrics
    LLM_CALLS_TOTAL.labels(task=task, model=resolved_model, workspace_id=workspace_id).inc()
    LLM_TOKENS_TOTAL.labels(direction="input", model=resolved_model, workspace_id=workspace_id).inc(input_tokens)
    LLM_TOKENS_TOTAL.labels(direction="output", model=resolved_model, workspace_id=workspace_id).inc(output_tokens)
    LLM_COST_USD.labels(task=task, model=resolved_model, workspace_id=workspace_id).inc(cost)
    LLM_CALL_DURATION.labels(task=task, model=resolved_model).observe(_call_duration)

    # Extract text from the first content block
    text: str = response.content[0].text
    return text
