"""Apollo.io MCP adapter for OmniGTM.

Wraps Apollo MCP tool calls in the BaseTool interface so they can be
used by qualification nodes. Falls back to the HTTP-based ApolloSearchTool
when MCP is not available.

MCP tools are invoked via subprocess call to the Claude CLI, or directly
if running inside Claude Code. For production use outside Claude Code,
falls back to the HTTP API.
"""

from __future__ import annotations

from typing import Any

from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.apollo_search import ApolloSearchTool


class ApolloMCPAdapter:
    """Adapter that wraps Apollo MCP tool calls in a unified interface.

    Provides high-level methods for contact search, org enrichment,
    company search, and job postings. Falls back to the HTTP-based
    ``ApolloSearchTool`` when MCP is unavailable.

    Parameters
    ----------
    rate_limiter:
        Shared RateLimiter instance for enforcing API quotas.
    use_mcp:
        When ``True``, format requests as MCP tool call payloads.
        Defaults to ``settings.APOLLO_MCP_ENABLED``.
    """

    def __init__(
        self,
        rate_limiter: RateLimiter,
        use_mcp: bool | None = None,
    ) -> None:
        self.rate_limiter = rate_limiter
        self.use_mcp = use_mcp if use_mcp is not None else settings.APOLLO_MCP_ENABLED
        self._http_tool = ApolloSearchTool(rate_limiter)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search_contacts(
        self,
        domain: str,
        workspace_id: str,
        titles: list[str] | None = None,
        limit: int = 10,
        plan: str = "pro",
    ) -> list[dict[str, Any]]:
        """Search for contacts at *domain*, optionally filtered by *titles*.

        Returns a list of contact dicts normalised to the Contact model
        shape: ``{id, email, first_name, last_name, role, linkedin_url,
        phone, account_id}``.
        """
        log.info(
            "apollo_mcp.search_contacts.start",
            domain=domain,
            workspace_id=workspace_id,
            use_mcp=self.use_mcp,
        )

        await self.rate_limiter.enforce(workspace_id, "apollo", plan)

        if self.use_mcp:
            try:
                raw = await self._mcp_contact_search(domain, titles, limit)
                contacts = self._normalize_contacts(raw, domain)
                log.info(
                    "apollo_mcp.search_contacts.complete",
                    workspace_id=workspace_id,
                    method="mcp",
                    result_count=len(contacts),
                )
                return contacts
            except Exception as exc:
                log.warning(
                    "apollo_mcp.search_contacts.mcp_failed",
                    workspace_id=workspace_id,
                    error=str(exc),
                )

        # Fallback: HTTP-based ApolloSearchTool
        try:
            filters: dict[str, Any] = {
                "q_organization_domains": domain,
                "per_page": limit,
            }
            if titles:
                filters["person_titles"] = titles

            raw_contacts = await self._http_tool.run(
                query=domain,
                workspace_id=workspace_id,
                plan=plan,
                filters=filters,
            )
            contacts = self._normalize_contacts(raw_contacts, domain)
            log.info(
                "apollo_mcp.search_contacts.complete",
                workspace_id=workspace_id,
                method="http_fallback",
                result_count=len(contacts),
            )
            return contacts
        except Exception as exc:
            log.error(
                "apollo_mcp.search_contacts.failed",
                workspace_id=workspace_id,
                error=str(exc),
            )
            return []

    async def enrich_organization(
        self,
        domain: str,
        workspace_id: str,
        plan: str = "pro",
    ) -> dict[str, Any]:
        """Enrich organisation data for *domain*.

        Returns a dict with keys: ``company_name``, ``domain``,
        ``industry``, ``employee_count``, ``revenue``, ``founded_year``,
        ``technologies``, ``description``, ``headquarters``.
        """
        log.info(
            "apollo_mcp.enrich_organization.start",
            domain=domain,
            workspace_id=workspace_id,
            use_mcp=self.use_mcp,
        )

        await self.rate_limiter.enforce(workspace_id, "apollo", plan)

        if self.use_mcp:
            try:
                raw = await self._mcp_org_enrich(domain)
                result = self._normalize_org(raw)
                log.info(
                    "apollo_mcp.enrich_organization.complete",
                    workspace_id=workspace_id,
                    method="mcp",
                )
                return result
            except Exception as exc:
                log.warning(
                    "apollo_mcp.enrich_organization.mcp_failed",
                    workspace_id=workspace_id,
                    error=str(exc),
                )

        # Fallback: HTTP-based enrichment via ApolloSearchTool
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.APOLLO_BASE_URL}/organizations/enrich",
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache",
                        "X-Api-Key": settings.APOLLO_API_KEY,
                    },
                    params={"domain": domain},
                )

            if resp.status_code == 200:
                data = resp.json()
                org = data.get("organization", data)
                result = self._normalize_org(org)
                log.info(
                    "apollo_mcp.enrich_organization.complete",
                    workspace_id=workspace_id,
                    method="http_fallback",
                )
                return result
            else:
                log.warning(
                    "apollo_mcp.enrich_organization.http_error",
                    workspace_id=workspace_id,
                    status_code=resp.status_code,
                )
                return {}
        except Exception as exc:
            log.error(
                "apollo_mcp.enrich_organization.failed",
                workspace_id=workspace_id,
                error=str(exc),
            )
            return {}

    async def search_companies(
        self,
        query: str,
        workspace_id: str,
        filters: dict[str, Any] | None = None,
        plan: str = "pro",
    ) -> list[dict[str, Any]]:
        """Search for companies matching *query*.

        Returns a list of company dicts.
        """
        log.info(
            "apollo_mcp.search_companies.start",
            query=query,
            workspace_id=workspace_id,
            use_mcp=self.use_mcp,
        )

        await self.rate_limiter.enforce(workspace_id, "apollo", plan)

        if self.use_mcp:
            try:
                raw = await self._mcp_company_search(query, filters)
                companies = self._normalize_companies(raw)
                log.info(
                    "apollo_mcp.search_companies.complete",
                    workspace_id=workspace_id,
                    method="mcp",
                    result_count=len(companies),
                )
                return companies
            except Exception as exc:
                log.warning(
                    "apollo_mcp.search_companies.mcp_failed",
                    workspace_id=workspace_id,
                    error=str(exc),
                )

        # Fallback: HTTP API
        try:
            import httpx

            params: dict[str, Any] = {"q_organization_name": query}
            if filters:
                params.update(filters)

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.APOLLO_BASE_URL}/mixed_companies/search",
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache",
                        "X-Api-Key": settings.APOLLO_API_KEY,
                    },
                    json=params,
                )

            if resp.status_code == 200:
                data = resp.json()
                companies = self._normalize_companies(
                    data.get("organizations", data.get("accounts", []))
                )
                log.info(
                    "apollo_mcp.search_companies.complete",
                    workspace_id=workspace_id,
                    method="http_fallback",
                    result_count=len(companies),
                )
                return companies
            else:
                log.warning(
                    "apollo_mcp.search_companies.http_error",
                    workspace_id=workspace_id,
                    status_code=resp.status_code,
                )
                return []
        except Exception as exc:
            log.error(
                "apollo_mcp.search_companies.failed",
                workspace_id=workspace_id,
                error=str(exc),
            )
            return []

    async def get_job_postings(
        self,
        domain: str,
        workspace_id: str,
        plan: str = "pro",
    ) -> list[dict[str, Any]]:
        """Get job postings for the organisation at *domain*.

        Returns a list of ``{title, department, location, url}`` dicts.
        """
        log.info(
            "apollo_mcp.get_job_postings.start",
            domain=domain,
            workspace_id=workspace_id,
            use_mcp=self.use_mcp,
        )

        await self.rate_limiter.enforce(workspace_id, "apollo", plan)

        if self.use_mcp:
            try:
                raw = await self._mcp_job_postings(domain)
                postings = self._normalize_job_postings(raw)
                log.info(
                    "apollo_mcp.get_job_postings.complete",
                    workspace_id=workspace_id,
                    method="mcp",
                    posting_count=len(postings),
                )
                return postings
            except Exception as exc:
                log.warning(
                    "apollo_mcp.get_job_postings.mcp_failed",
                    workspace_id=workspace_id,
                    error=str(exc),
                )

        # Fallback: HTTP API
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{settings.APOLLO_BASE_URL}/organizations/job_postings",
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache",
                        "X-Api-Key": settings.APOLLO_API_KEY,
                    },
                    params={"organization_domain": domain},
                )

            if resp.status_code == 200:
                data = resp.json()
                raw_postings = data.get("job_postings", data.get("jobs", []))
                postings = self._normalize_job_postings(raw_postings)
                log.info(
                    "apollo_mcp.get_job_postings.complete",
                    workspace_id=workspace_id,
                    method="http_fallback",
                    posting_count=len(postings),
                )
                return postings
            else:
                log.warning(
                    "apollo_mcp.get_job_postings.http_error",
                    workspace_id=workspace_id,
                    status_code=resp.status_code,
                )
                return []
        except Exception as exc:
            log.error(
                "apollo_mcp.get_job_postings.failed",
                workspace_id=workspace_id,
                error=str(exc),
            )
            return []

    # ------------------------------------------------------------------
    # MCP tool call formatters
    # ------------------------------------------------------------------

    async def _mcp_contact_search(
        self,
        domain: str,
        titles: list[str] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Format and execute an MCP contact search call.

        When running inside Claude Code, MCP tools are available as
        native tool calls. Outside that environment this raises
        ``NotImplementedError`` so the caller falls back to HTTP.
        """
        payload: dict[str, Any] = {
            "tool": "mcp__claude_ai_Apollo_io__apollo_mixed_people_api_search",
            "params": {
                "q_organization_domains": domain,
                "per_page": limit,
            },
        }
        if titles:
            payload["params"]["person_titles"] = titles

        # MCP tools are not callable from Python runtime — signal
        # fallback to HTTP.
        raise NotImplementedError(
            "MCP tools are only available inside the Claude Code environment"
        )

    async def _mcp_org_enrich(self, domain: str) -> dict[str, Any]:
        """Format and execute an MCP org enrichment call."""
        raise NotImplementedError(
            "MCP tools are only available inside the Claude Code environment"
        )

    async def _mcp_company_search(
        self,
        query: str,
        filters: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Format and execute an MCP company search call."""
        raise NotImplementedError(
            "MCP tools are only available inside the Claude Code environment"
        )

    async def _mcp_job_postings(self, domain: str) -> list[dict[str, Any]]:
        """Format and execute an MCP job postings call."""
        raise NotImplementedError(
            "MCP tools are only available inside the Claude Code environment"
        )

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_contacts(
        raw: list[dict[str, Any]],
        domain: str,
    ) -> list[dict[str, Any]]:
        """Map Apollo contact fields to the Contact model shape."""
        contacts: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            contact = {
                "id": item.get("id", ""),
                "email": item.get("email", ""),
                "first_name": item.get("first_name", ""),
                "last_name": item.get("last_name", ""),
                "role": item.get("title", item.get("headline", "")),
                "linkedin_url": item.get("linkedin_url", ""),
                "phone": (
                    item.get("phone_number")
                    or (item.get("phone_numbers", [None]) or [None])[0]
                    or ""
                ),
                "account_id": item.get("organization_id", item.get("account_id", "")),
                "domain": domain,
            }
            contacts.append(contact)
        return contacts

    @staticmethod
    def _normalize_org(raw: dict[str, Any]) -> dict[str, Any]:
        """Map Apollo organisation fields to enriched org shape."""
        if not raw:
            return {}

        # Handle nested 'organization' key from Apollo API responses
        org = raw.get("organization", raw) if isinstance(raw, dict) else raw

        return {
            "company_name": org.get("name", ""),
            "domain": org.get("primary_domain", org.get("domain", "")),
            "industry": org.get("industry", ""),
            "employee_count": org.get(
                "estimated_num_employees",
                org.get("employee_count"),
            ),
            "revenue": org.get(
                "annual_revenue",
                org.get("estimated_annual_revenue"),
            ),
            "founded_year": org.get("founded_year"),
            "technologies": org.get("current_technologies", []),
            "description": org.get("short_description", org.get("description", "")),
            "headquarters": org.get(
                "raw_address",
                org.get("city", ""),
            ),
        }

    @staticmethod
    def _normalize_companies(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalise a list of Apollo company results."""
        companies: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            companies.append(
                {
                    "company_name": item.get("name", ""),
                    "domain": item.get("primary_domain", item.get("domain", "")),
                    "industry": item.get("industry", ""),
                    "employee_count": item.get(
                        "estimated_num_employees",
                        item.get("employee_count"),
                    ),
                    "description": item.get(
                        "short_description", item.get("description", "")
                    ),
                }
            )
        return companies

    @staticmethod
    def _normalize_job_postings(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalise Apollo job postings to ``{title, department, location, url}``."""
        postings: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            postings.append(
                {
                    "title": item.get("title", ""),
                    "department": item.get(
                        "department", item.get("category", "")
                    ),
                    "location": item.get("location", ""),
                    "url": item.get("url", item.get("link", "")),
                }
            )
        return postings
