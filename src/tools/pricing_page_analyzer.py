"""PricingPageAnalyzerTool — scrapes and analyzes pricing pages via n8n webhook."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class PricingPageError(Exception):
    """Raised on pricing page analysis failures (including 429 and 401)."""


class PricingPageAnalyzerTool(BaseTool):
    """Scrapes and analyzes pricing pages to extract pricing model intelligence.

    Uses the n8n web scraper webhook to fetch page content, then parses
    pricing signals from the raw HTML/text.

    Input: url of the pricing page.
    Output: dict with pricing analysis results.
    """

    RESOURCE_NAME = "web_scraper"

    def __init__(self, rate_limiter: RateLimiter) -> None:
        super().__init__(rate_limiter)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def run(
        self,
        url: str,
        workspace_id: str,
        plan: str,
    ) -> dict[str, Any]:
        """Scrape and analyze the pricing page at *url*.

        Parameters
        ----------
        url:
            The URL of the pricing page to analyze.
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace.

        Returns
        -------
        dict[str, Any]
            Dict with keys: ``url``, ``has_pricing_page``, ``pricing_models``,
            ``tiers``, ``has_enterprise``, ``has_usage_based``,
            ``has_custom_pricing``, ``raw_content``.
        """
        log.info(
            "pricing_page_analyzer.start",
            url=url,
            workspace_id=workspace_id,
        )

        # 1. Rate limit check FIRST
        await self.rate_limiter.enforce(workspace_id, self.RESOURCE_NAME, plan)

        # 2. HTTP call with timeout (longer timeout for scraping)
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.N8N_WEBHOOK_BASE_URL}/web-scrape",
                headers={
                    "Content-Type": "application/json",
                    "X-Workspace-Id": workspace_id,
                },
                json={"url": url},
            )

        # 3. Specific error handling
        if resp.status_code == 429:
            raise PricingPageError(
                f"Rate limited by web scraper for workspace {workspace_id}"
            )
        if resp.status_code == 401:
            raise PricingPageError("Invalid web scraper credentials")
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        content = data.get("content", data.get("text", ""))
        content_lower = content.lower()

        # 4. Extract pricing signals from raw content
        pricing_models = _detect_pricing_models(content_lower)
        tiers = _detect_tiers(content_lower)

        result: dict[str, Any] = {
            "url": url,
            "has_pricing_page": bool(content and _looks_like_pricing(content_lower)),
            "pricing_models": pricing_models,
            "tiers": tiers,
            "has_enterprise": _has_enterprise(content_lower),
            "has_usage_based": _has_usage_based(content_lower),
            "has_custom_pricing": _has_custom_pricing(content_lower),
            "raw_content": content,
        }

        log.info(
            "pricing_page_analyzer.complete",
            workspace_id=workspace_id,
            url=url,
            has_pricing_page=result["has_pricing_page"],
            model_count=len(pricing_models),
            tier_count=len(tiers),
        )

        return result


# ---------------------------------------------------------------------------
# Private helpers for pricing signal detection
# ---------------------------------------------------------------------------

_PRICING_KEYWORDS = ["pricing", "plans", "price", "cost", "subscription", "billing"]

_MODEL_SIGNALS: dict[str, list[str]] = {
    "per_seat": ["per seat", "per user", "per license", "/user", "/seat"],
    "flat_rate": ["flat rate", "flat fee", "fixed price", "one price"],
    "usage_based": ["usage-based", "usage based", "pay as you go", "metered", "per api call"],
    "tiered": ["starter", "professional", "enterprise", "basic", "pro", "growth"],
    "freemium": ["free plan", "free tier", "free forever", "get started free"],
}

_TIER_KEYWORDS = [
    "free", "starter", "basic", "essentials", "growth", "professional",
    "pro", "business", "enterprise", "premium", "scale", "team", "plus",
]


def _looks_like_pricing(content: str) -> bool:
    return any(kw in content for kw in _PRICING_KEYWORDS)


def _detect_pricing_models(content: str) -> list[str]:
    models = []
    for model_name, signals in _MODEL_SIGNALS.items():
        if any(signal in content for signal in signals):
            models.append(model_name)
    return models


def _detect_tiers(content: str) -> list[str]:
    return [tier for tier in _TIER_KEYWORDS if tier in content]


def _has_enterprise(content: str) -> bool:
    return "enterprise" in content or "contact sales" in content or "talk to sales" in content


def _has_usage_based(content: str) -> bool:
    return any(s in content for s in _MODEL_SIGNALS["usage_based"])


def _has_custom_pricing(content: str) -> bool:
    return any(
        phrase in content
        for phrase in ["custom pricing", "contact us", "contact sales", "talk to sales", "get a quote", "request a quote"]
    )
