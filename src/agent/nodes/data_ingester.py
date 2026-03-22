"""data_ingester node — pulls accounts and contacts from CRM into state.

Reads raw_accounts from state (list of dicts from CRM), fetches contacts
per account via the CRM reader tool, and returns typed Account + Contact lists.

When ``settings.USE_APOLLO_ENRICHMENT`` is enabled, enriches each account
with firmographic data and discovers additional contacts via the
``ApolloMCPAdapter``.
"""

from __future__ import annotations

from src.agent.state import Account, Contact, QualificationState
from src.config import settings
from src.logger import log
from src.ratelimit.bucket import RateLimiter

# Module-level tool instance — RateLimiter is injected at startup
_rate_limiter: RateLimiter | None = None


def init_tools(rate_limiter: RateLimiter) -> None:
    """Inject the shared RateLimiter (called once at app startup)."""
    global _rate_limiter
    _rate_limiter = rate_limiter


def _get_crm_reader():
    """Lazy-import CRM reader tool to avoid circular imports."""
    if _rate_limiter is None:
        raise RuntimeError(
            "data_ingester tools not initialised — call init_tools() first"
        )
    from src.tools.crm_reader import CRMReaderTool

    return CRMReaderTool(_rate_limiter)


def _get_apollo_adapter():
    """Lazy-import ApolloMCPAdapter to avoid circular imports."""
    if _rate_limiter is None:
        raise RuntimeError(
            "data_ingester tools not initialised — call init_tools() first"
        )
    from src.tools.apollo_mcp import ApolloMCPAdapter

    return ApolloMCPAdapter(_rate_limiter)


# Default ICP roles to search when discovering contacts via Apollo
_ICP_ROLES: list[str] = [
    "VP Revenue Operations",
    "Head of Pricing",
    "VP Finance",
    "Chief Revenue Officer",
    "Director of Sales Operations",
    "Head of Monetization",
    "VP Strategy",
    "CFO",
]


async def data_ingester(state: QualificationState) -> dict:
    """Ingest raw account data from CRM and return typed Account + Contact lists."""
    thread_id = state["thread_id"]
    workspace_id = state["workspace_id"]
    log.info("data_ingester.start", thread_id=thread_id, workspace_id=workspace_id)

    crm_reader = _get_crm_reader()

    # Determine raw accounts source
    raw_accounts: list[dict] = state.get("raw_accounts") or []

    # If no raw_accounts provided, try to pull from campaign ICP criteria
    if not raw_accounts:
        campaign = state.get("campaign")
        if campaign and campaign.icp_criteria:
            log.info(
                "data_ingester.pulling_from_icp",
                thread_id=thread_id,
                workspace_id=workspace_id,
            )
            try:
                raw_accounts = await crm_reader.run(
                    query_type="icp_search",
                    criteria=campaign.icp_criteria,
                    workspace_id=workspace_id,
                    plan="pro",
                )
            except Exception as exc:
                log.error(
                    "data_ingester.icp_pull_failed",
                    thread_id=thread_id,
                    workspace_id=workspace_id,
                    error=str(exc),
                )
                return {"error": f"Failed to pull accounts from ICP: {exc}"}

    if not raw_accounts:
        log.warning(
            "data_ingester.no_accounts",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        return {"accounts": [], "contacts": [], "error": "No raw accounts to ingest"}

    # Optionally initialise the Apollo adapter for enrichment
    apollo_adapter = None
    if settings.USE_APOLLO_ENRICHMENT:
        try:
            apollo_adapter = _get_apollo_adapter()
        except Exception as exc:
            log.warning(
                "data_ingester.apollo_adapter_init_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                error=str(exc),
            )

    accounts: list[Account] = []
    all_contacts: list[Contact] = []

    for raw in raw_accounts:
        # Build typed Account
        account = Account(
            id=raw.get("id", ""),
            workspace_id=workspace_id,
            company_name=raw.get("company_name", raw.get("name", "")),
            domain=raw.get("domain"),
            industry=raw.get("industry"),
            employee_count=raw.get("employee_count"),
            revenue=raw.get("revenue"),
            metadata=raw.get("metadata", {}),
        )

        # --- Apollo enrichment: fill in missing firmographic fields ---
        if apollo_adapter and account.domain:
            try:
                enriched = await apollo_adapter.enrich_organization(
                    domain=account.domain,
                    workspace_id=workspace_id,
                )
                if enriched:
                    account = _merge_enrichment(account, enriched)
                    log.info(
                        "data_ingester.apollo_enrichment_applied",
                        thread_id=thread_id,
                        workspace_id=workspace_id,
                        account_id=account.id,
                        domain=account.domain,
                    )
            except Exception as exc:
                log.warning(
                    "data_ingester.apollo_enrichment_failed",
                    thread_id=thread_id,
                    workspace_id=workspace_id,
                    account_id=account.id,
                    error=str(exc),
                )

        accounts.append(account)

        # Fetch contacts for this account from CRM
        try:
            contact_dicts = await crm_reader.run(
                query_type="contacts_by_account",
                account_id=account.id,
                workspace_id=workspace_id,
                plan="pro",
            )
            for cd in contact_dicts or []:
                contact = Contact(
                    id=cd.get("id", ""),
                    workspace_id=workspace_id,
                    account_id=account.id,
                    email=cd.get("email", ""),
                    first_name=cd.get("first_name"),
                    last_name=cd.get("last_name"),
                    role=cd.get("role", cd.get("title")),
                    linkedin_url=cd.get("linkedin_url"),
                    phone=cd.get("phone"),
                )
                all_contacts.append(contact)
        except Exception as exc:
            log.warning(
                "data_ingester.contact_fetch_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                account_id=account.id,
                error=str(exc),
            )
            # Continue with other accounts even if one fails

        # --- Apollo contact discovery: find additional contacts ---
        if apollo_adapter and account.domain:
            try:
                apollo_contacts = await apollo_adapter.search_contacts(
                    domain=account.domain,
                    workspace_id=workspace_id,
                    titles=_ICP_ROLES,
                    limit=10,
                )
                existing_emails = {c.email.lower() for c in all_contacts if c.account_id == account.id}
                for ac in apollo_contacts:
                    email = ac.get("email", "")
                    if not email or email.lower() in existing_emails:
                        continue
                    contact = Contact(
                        id=ac.get("id", ""),
                        workspace_id=workspace_id,
                        account_id=account.id,
                        email=email,
                        first_name=ac.get("first_name"),
                        last_name=ac.get("last_name"),
                        role=ac.get("role"),
                        linkedin_url=ac.get("linkedin_url"),
                        phone=ac.get("phone"),
                    )
                    all_contacts.append(contact)
                    existing_emails.add(email.lower())

                log.info(
                    "data_ingester.apollo_contacts_discovered",
                    thread_id=thread_id,
                    workspace_id=workspace_id,
                    account_id=account.id,
                    new_contacts=len(apollo_contacts),
                )
            except Exception as exc:
                log.warning(
                    "data_ingester.apollo_contact_search_failed",
                    thread_id=thread_id,
                    workspace_id=workspace_id,
                    account_id=account.id,
                    error=str(exc),
                )

    log.info(
        "data_ingester.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        account_count=len(accounts),
        contact_count=len(all_contacts),
    )
    return {"accounts": accounts, "contacts": all_contacts}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _merge_enrichment(account: Account, enriched: dict) -> Account:
    """Merge Apollo enrichment into an Account without overwriting existing values.

    Non-``None`` fields on *account* are preserved; only ``None`` fields
    are populated from *enriched*.
    """
    updates: dict = {}

    if account.industry is None and enriched.get("industry"):
        updates["industry"] = enriched["industry"]

    if account.employee_count is None and enriched.get("employee_count") is not None:
        updates["employee_count"] = enriched["employee_count"]

    if account.revenue is None and enriched.get("revenue") is not None:
        updates["revenue"] = enriched["revenue"]

    # Merge technologies and other metadata into account.metadata
    metadata = dict(account.metadata)
    if enriched.get("technologies"):
        metadata.setdefault("technologies", enriched["technologies"])
    if enriched.get("founded_year"):
        metadata.setdefault("founded_year", enriched["founded_year"])
    if enriched.get("description"):
        metadata.setdefault("description", enriched["description"])
    if enriched.get("headquarters"):
        metadata.setdefault("headquarters", enriched["headquarters"])
    if enriched.get("company_name") and not account.company_name:
        updates["company_name"] = enriched["company_name"]

    if metadata != account.metadata:
        updates["metadata"] = metadata

    if updates:
        return account.model_copy(update=updates)
    return account
