"""Domain normalization and company deduplication.

Pure rules — no LLM calls. Handles:
- Domain canonicalization (strip www, trailing slashes, protocols)
- Known alias resolution
- Company name fuzzy matching
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Known domain aliases (add more as discovered)
DOMAIN_ALIASES: dict[str, str] = {
    "google.com": "google.com",
    "alphabet.com": "google.com",
    "googleapis.com": "google.com",
    "microsoft.com": "microsoft.com",
    "azure.com": "microsoft.com",
    "github.com": "microsoft.com",
    "linkedin.com": "microsoft.com",
    "meta.com": "meta.com",
    "facebook.com": "meta.com",
    "instagram.com": "meta.com",
    "salesforce.com": "salesforce.com",
    "heroku.com": "salesforce.com",
    "slack.com": "salesforce.com",
    "mulesoft.com": "salesforce.com",
}


def normalize_domain(raw: str) -> str:
    """Normalize a domain string to a canonical form.

    Examples:
        "https://www.acme.com/pricing" → "acme.com"
        "WWW.Acme.COM" → "acme.com"
        "acme.com." → "acme.com"
    """
    if not raw:
        return ""

    domain = raw.strip().lower()

    # Handle full URLs
    if "://" in domain:
        parsed = urlparse(domain)
        domain = parsed.hostname or domain
    elif "/" in domain:
        domain = domain.split("/")[0]

    # Strip www prefix, trailing dots
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.rstrip(".")

    # Resolve known aliases
    return DOMAIN_ALIASES.get(domain, domain)


def domains_match(domain_a: str, domain_b: str) -> bool:
    """Check if two domain strings refer to the same entity."""
    return normalize_domain(domain_a) == normalize_domain(domain_b)


def _clean_company_name(name: str) -> str:
    """Strip common suffixes and normalize for comparison."""
    name = name.strip().lower()
    # Remove common corporate suffixes
    suffixes = [
        r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|"
        r"llp|gmbh|ag|sa|bv|pty|plc|se)\b\.?",
    ]
    for pattern in suffixes:
        name = re.sub(pattern, "", name)
    # Normalize whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def company_names_similar(name_a: str, name_b: str, threshold: float = 0.85) -> bool:
    """Check if two company names likely refer to the same entity.

    Uses character-level bigram similarity (Dice coefficient).
    """
    clean_a = _clean_company_name(name_a)
    clean_b = _clean_company_name(name_b)

    if clean_a == clean_b:
        return True

    if not clean_a or not clean_b:
        return False

    # Bigram Dice coefficient
    bigrams_a = {clean_a[i : i + 2] for i in range(len(clean_a) - 1)}
    bigrams_b = {clean_b[i : i + 2] for i in range(len(clean_b) - 1)}

    if not bigrams_a or not bigrams_b:
        return False

    overlap = len(bigrams_a & bigrams_b)
    dice = 2 * overlap / (len(bigrams_a) + len(bigrams_b))
    return dice >= threshold


def deduplicate_accounts(
    accounts: list[dict],
    domain_key: str = "domain",
    name_key: str = "company_name",
) -> list[dict]:
    """Deduplicate a list of account dicts by domain, then by name similarity.

    Returns deduplicated list, preserving the first occurrence.
    Merges metadata from duplicates into the surviving record.
    """
    seen_domains: dict[str, int] = {}
    result: list[dict] = []

    for account in accounts:
        domain = normalize_domain(account.get(domain_key, "") or "")
        name = account.get(name_key, "") or ""

        # Check domain match
        if domain and domain in seen_domains:
            # Merge metadata into existing
            idx = seen_domains[domain]
            _merge_metadata(result[idx], account)
            continue

        # Check name similarity against existing
        matched = False
        for i, existing in enumerate(result):
            existing_name = existing.get(name_key, "") or ""
            if name and existing_name and company_names_similar(name, existing_name):
                _merge_metadata(existing, account)
                matched = True
                break

        if not matched:
            if domain:
                seen_domains[domain] = len(result)
            result.append(dict(account))

    return result


def _merge_metadata(target: dict, source: dict) -> None:
    """Merge non-None fields from source into target without overwriting."""
    for key, value in source.items():
        if value is not None and target.get(key) is None:
            target[key] = value
    # Merge metadata dicts
    if "metadata" in source and isinstance(source["metadata"], dict):
        if "metadata" not in target or not isinstance(target["metadata"], dict):
            target["metadata"] = {}
        for k, v in source["metadata"].items():
            if k not in target["metadata"]:
                target["metadata"][k] = v
