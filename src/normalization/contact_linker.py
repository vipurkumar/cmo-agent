"""Contact-to-account linking with confidence scoring.

Links contacts to accounts using domain matching and name heuristics.
No LLM calls — pure deterministic logic.
"""

from __future__ import annotations

import re

from src.agent.state import Account, Contact
from src.normalization.domain_resolver import normalize_domain


def _extract_domain_from_email(email: str) -> str:
    """Extract and normalize domain from email address."""
    if not email or "@" not in email:
        return ""
    return normalize_domain(email.split("@", 1)[1])


def _is_generic_email(email: str) -> bool:
    """Check if email is from a generic provider (not company domain)."""
    generic_domains = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "aol.com", "icloud.com", "mail.com", "protonmail.com",
        "zoho.com", "yandex.com",
    }
    domain = _extract_domain_from_email(email)
    return domain in generic_domains


def link_confidence(contact: Contact, account: Account) -> float:
    """Compute confidence score (0.0–1.0) that a contact belongs to an account.

    Scoring:
    - Email domain matches account domain: 0.95
    - Email domain matches but generic provider: 0.20
    - No email domain match, but account_id matches: 0.80
    - LinkedIn URL contains company name: 0.40
    - No matching signals: 0.10
    """
    confidence = 0.10

    if not contact.email:
        # Only account_id link
        if contact.account_id == account.id:
            return 0.80
        return confidence

    email_domain = _extract_domain_from_email(contact.email)
    account_domain = normalize_domain(account.domain or "")

    # Strong match: email domain == account domain
    if email_domain and account_domain and email_domain == account_domain:
        if _is_generic_email(contact.email):
            confidence = max(confidence, 0.20)
        else:
            confidence = max(confidence, 0.95)

    # Account ID match
    if contact.account_id == account.id:
        confidence = max(confidence, 0.80)

    # LinkedIn heuristic
    if contact.linkedin_url and account.company_name:
        company_slug = re.sub(r"[^a-z0-9]", "", account.company_name.lower())
        linkedin_lower = contact.linkedin_url.lower()
        if company_slug and company_slug in linkedin_lower:
            confidence = max(confidence, 0.40)

    return confidence


def link_contacts_to_account(
    contacts: list[Contact],
    account: Account,
    min_confidence: float = 0.50,
) -> list[tuple[Contact, float]]:
    """Link contacts to an account, returning (contact, confidence) pairs.

    Only returns contacts above min_confidence threshold.
    Results are sorted by confidence descending.
    """
    linked: list[tuple[Contact, float]] = []

    for contact in contacts:
        conf = link_confidence(contact, account)
        if conf >= min_confidence:
            linked.append((contact, conf))

    linked.sort(key=lambda x: x[1], reverse=True)
    return linked


def deduplicate_contacts(contacts: list[Contact]) -> list[Contact]:
    """Deduplicate contacts by email, preserving the most complete record."""
    seen_emails: dict[str, Contact] = {}

    for contact in contacts:
        email_lower = contact.email.lower().strip()
        if email_lower not in seen_emails:
            seen_emails[email_lower] = contact
        else:
            # Merge: prefer non-None fields from newer record
            existing = seen_emails[email_lower]
            merged = existing.model_copy(update={
                k: v
                for k, v in contact.model_dump().items()
                if v is not None and getattr(existing, k) is None
            })
            seen_emails[email_lower] = merged

    return list(seen_emails.values())
