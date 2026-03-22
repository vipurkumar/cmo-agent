"""Demo tool implementations — realistic canned data, no HTTP calls."""

from __future__ import annotations

import uuid
from typing import Any

from src.logger import log
from src.tools.base import BaseTool


class _NoOpRateLimiter:
    """Placeholder that satisfies BaseTool.__init__ without Redis."""

    async def enforce(self, workspace_id: str, resource: str, plan: str) -> None:
        pass


_noop_rl = _NoOpRateLimiter()


class DemoApolloSearchTool(BaseTool):
    def __init__(self, rate_limiter: Any = None) -> None:
        super().__init__(rate_limiter or _noop_rl)

    async def run(
        self,
        query: str,
        workspace_id: str,
        plan: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        log.info("demo.apollo_search.run", query=query, workspace_id=workspace_id)

        _CONTACTS: dict[str, list[dict[str, Any]]] = {
            "NovaPay Technologies": [
                {
                    "id": "apollo-np-001",
                    "first_name": "Ravi",
                    "last_name": "Kapoor",
                    "title": "VP of Product & Monetization",
                    "email": "r.kapoor@novapaytech.com",
                    "linkedin_url": "https://linkedin.com/in/ravikapoor-demo",
                    "organization": {"name": "NovaPay Technologies", "estimated_num_employees": 420},
                },
                {
                    "id": "apollo-np-002",
                    "first_name": "Ananya",
                    "last_name": "Desai",
                    "title": "Director of Billing Engineering",
                    "email": "a.desai@novapaytech.com",
                    "linkedin_url": "https://linkedin.com/in/ananyad-demo",
                    "organization": {"name": "NovaPay Technologies", "estimated_num_employees": 420},
                },
                {
                    "id": "apollo-np-003",
                    "first_name": "David",
                    "last_name": "Okafor",
                    "title": "CFO",
                    "email": "d.okafor@novapaytech.com",
                    "linkedin_url": "https://linkedin.com/in/davidokafor-demo",
                    "organization": {"name": "NovaPay Technologies", "estimated_num_employees": 420},
                },
            ],
            "MediCloud AI": [
                {
                    "id": "apollo-mc-001",
                    "first_name": "Lisa",
                    "last_name": "Tang",
                    "title": "Head of Revenue Operations",
                    "email": "lisa.tang@medicloud.ai",
                    "linkedin_url": "https://linkedin.com/in/lisatang-demo",
                    "organization": {"name": "MediCloud AI", "estimated_num_employees": 280},
                },
                {
                    "id": "apollo-mc-002",
                    "first_name": "Arjun",
                    "last_name": "Mehta",
                    "title": "VP of Finance",
                    "email": "a.mehta@medicloud.ai",
                    "linkedin_url": "https://linkedin.com/in/arjunm-demo",
                    "organization": {"name": "MediCloud AI", "estimated_num_employees": 280},
                },
                {
                    "id": "apollo-mc-003",
                    "first_name": "Sarah",
                    "last_name": "Williams",
                    "title": "Director of Platform Engineering",
                    "email": "s.williams@medicloud.ai",
                    "linkedin_url": "https://linkedin.com/in/sarahw-demo",
                    "organization": {"name": "MediCloud AI", "estimated_num_employees": 280},
                },
            ],
        }

        return _CONTACTS.get(query, [
            {
                "id": "apollo-gen-001",
                "first_name": "Demo",
                "last_name": "Contact",
                "title": "VP of Revenue",
                "email": f"contact@{query.lower().replace(' ', '')}.com",
                "linkedin_url": "https://linkedin.com/in/demo",
                "organization": {"name": query, "estimated_num_employees": 200},
            },
        ])


class DemoNewsSearchTool(BaseTool):
    def __init__(self, rate_limiter: Any = None) -> None:
        super().__init__(rate_limiter or _noop_rl)

    async def run(
        self,
        company: str,
        workspace_id: str,
        plan: str,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        log.info("demo.news_search.run", company=company, workspace_id=workspace_id)

        _NEWS: dict[str, list[dict[str, Any]]] = {
            "NovaPay Technologies": [
                {
                    "title": "NovaPay Raises $58M Series B to Scale Embedded Finance Platform",
                    "url": "https://yourstory.example.com/novapay-series-b",
                    "date": "2026-02-20",
                    "summary": "NovaPay Technologies closed a $58M Series B led by Tiger Global and Accel India to expand embedded lending and payments APIs across Southeast Asia.",
                },
                {
                    "title": "NovaPay Launches Usage-Based Pricing for API Suite",
                    "url": "https://finextra.example.com/novapay-usage-pricing",
                    "date": "2026-01-15",
                    "summary": "NovaPay introduced usage-based pricing tiers for its BaaS APIs, moving away from flat per-partner fees to metered billing per API call.",
                },
                {
                    "title": "NovaPay CEO: 'Our Billing Infrastructure Can't Keep Up'",
                    "url": "https://economictimes.example.com/novapay-ceo-interview",
                    "date": "2026-03-05",
                    "summary": "In an interview with ET, NovaPay CEO acknowledged that scaling usage-based billing across 40+ fintech partners has exposed critical gaps in their billing stack.",
                },
            ],
            "MediCloud AI": [
                {
                    "title": "MediCloud AI Gets FDA Clearance for AI Pathology in 12 Cancer Types",
                    "url": "https://fiercehealthcare.example.com/medicloud-fda",
                    "date": "2026-02-10",
                    "summary": "MediCloud AI received FDA 510(k) clearance for its AI-powered pathology module, covering diagnostic support for 12 cancer types across histopathology workflows.",
                },
                {
                    "title": "MediCloud Pilots Outcome-Based Pricing: Hospitals Pay Per Accurate Diagnosis",
                    "url": "https://healthcaredive.example.com/medicloud-outcome-pricing",
                    "date": "2026-03-01",
                    "summary": "MediCloud AI announced a pilot program where hospitals pay based on diagnostic accuracy rather than per-seat licenses, a first in healthcare AI pricing.",
                },
                {
                    "title": "MediCloud AI Closes $35M Series A Extension",
                    "url": "https://techcrunch.example.com/medicloud-series-a-ext",
                    "date": "2026-01-22",
                    "summary": "MediCloud AI raised $35M in a Series A extension from GV and Khosla Ventures to accelerate its AI clinical decision support platform across 150+ hospitals.",
                },
            ],
        }

        return _NEWS.get(company, [
            {
                "title": f"{company} Announces New Product Launch",
                "url": f"https://news.example.com/{company.lower().replace(' ', '-')}",
                "date": "2026-03-01",
                "summary": f"{company} has launched new offerings with complex pricing models.",
            },
        ])


class DemoSlackApprovalTool(BaseTool):
    """Auto-approves in demo mode so the graph runs end-to-end."""

    def __init__(self, rate_limiter: Any = None) -> None:
        super().__init__(rate_limiter or _noop_rl)

    async def run(
        self,
        message_draft: dict[str, str],
        workspace_id: str,
        plan: str,
        channel: str,
    ) -> dict[str, Any]:
        log.info(
            "demo.slack_approval.auto_approved",
            workspace_id=workspace_id,
            channel=channel,
            subject=message_draft.get("subject", ""),
        )
        return {
            "status": "approved",
            "message_ts": f"demo-ts-{uuid.uuid4().hex[:8]}",
            "channel": channel,
        }


class DemoHubSpotTool(BaseTool):
    def __init__(self, rate_limiter: Any = None) -> None:
        super().__init__(rate_limiter or _noop_rl)

    async def run(
        self,
        operation: str,
        workspace_id: str,
        plan: str,
        object_type: str = "contacts",
        record_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        log.info(
            "demo.hubspot.run",
            operation=operation,
            object_type=object_type,
            workspace_id=workspace_id,
        )
        return {
            "id": record_id or f"hs-{uuid.uuid4().hex[:8]}",
            "properties": properties or {},
            "object_type": object_type,
            "operation": operation,
        }
