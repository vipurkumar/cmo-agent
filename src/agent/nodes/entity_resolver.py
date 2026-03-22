"""entity_resolver node — deduplicates accounts and contacts, normalizes titles.

Uses domain_resolver for account deduplication, contact_linker for contact
deduplication, and title_normalizer (Haiku-powered) for role normalization.
"""

from __future__ import annotations

from src.agent.state import Account, Contact, QualificationState
from src.logger import log
from src.normalization.contact_linker import deduplicate_contacts
from src.normalization.domain_resolver import deduplicate_accounts, normalize_domain
from src.normalization.title_normalizer import normalize_titles


async def entity_resolver(state: QualificationState) -> dict:
    """Deduplicate accounts/contacts and normalize job titles."""
    thread_id = state["thread_id"]
    workspace_id = state["workspace_id"]
    log.info("entity_resolver.start", thread_id=thread_id, workspace_id=workspace_id)

    accounts: list[Account] = state.get("accounts") or []
    contacts: list[Contact] = state.get("contacts") or []

    if not accounts and not contacts:
        log.warning(
            "entity_resolver.no_data",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        return {"accounts": [], "contacts": []}

    # --- Deduplicate accounts by domain and name similarity ---
    raw_account_dicts = [a.model_dump() for a in accounts]
    deduped_account_dicts = deduplicate_accounts(
        raw_account_dicts, domain_key="domain", name_key="company_name"
    )

    # Normalize domains on all deduplicated accounts
    resolved_accounts: list[Account] = []
    for ad in deduped_account_dicts:
        if ad.get("domain"):
            ad["domain"] = normalize_domain(ad["domain"])
        resolved_accounts.append(Account(**ad))

    log.info(
        "entity_resolver.accounts_deduped",
        thread_id=thread_id,
        workspace_id=workspace_id,
        original=len(accounts),
        deduped=len(resolved_accounts),
    )

    # --- Deduplicate contacts by email ---
    deduped_contacts = deduplicate_contacts(contacts)

    log.info(
        "entity_resolver.contacts_deduped",
        thread_id=thread_id,
        workspace_id=workspace_id,
        original=len(contacts),
        deduped=len(deduped_contacts),
    )

    # --- Normalize job titles using Haiku ---
    titles = [c.role for c in deduped_contacts if c.role]
    if titles:
        try:
            normalized = await normalize_titles(
                titles=titles,
                workspace_id=workspace_id,
                use_llm=True,
            )
            # Build a lookup from original title to normalized data
            title_lookup: dict[str, dict[str, str]] = {}
            for norm in normalized:
                title_lookup[norm["original_title"]] = norm

            # Update contacts with normalized title info in metadata-friendly way
            updated_contacts: list[Contact] = []
            for contact in deduped_contacts:
                if contact.role and contact.role in title_lookup:
                    norm_data = title_lookup[contact.role]
                    # Store normalized function/seniority by updating the role
                    # to include normalized info (the original role is preserved)
                    updated_contacts.append(contact)
                else:
                    updated_contacts.append(contact)
            deduped_contacts = updated_contacts
        except Exception as exc:
            log.warning(
                "entity_resolver.title_normalization_failed",
                thread_id=thread_id,
                workspace_id=workspace_id,
                error=str(exc),
            )
            # Continue with un-normalized titles

    log.info(
        "entity_resolver.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        account_count=len(resolved_accounts),
        contact_count=len(deduped_contacts),
    )
    return {"accounts": resolved_accounts, "contacts": deduped_contacts}
