"""Tests for OmniGTM normalization modules."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agent.state import Account, Contact
from src.normalization.domain_resolver import (
    company_names_similar,
    deduplicate_accounts,
    domains_match,
    normalize_domain,
)
from src.normalization.contact_linker import (
    deduplicate_contacts,
    link_confidence,
    link_contacts_to_account,
)
from src.normalization.title_normalizer import _rule_based_normalize


# ---------------------------------------------------------------------------
# Domain Resolver
# ---------------------------------------------------------------------------


class TestDomainNormalization:
    def test_strips_www(self):
        assert normalize_domain("www.acme.com") == "acme.com"

    def test_strips_protocol(self):
        assert normalize_domain("https://www.acme.com/pricing") == "acme.com"

    def test_strips_trailing_dot(self):
        assert normalize_domain("acme.com.") == "acme.com"

    def test_lowercases(self):
        assert normalize_domain("ACME.COM") == "acme.com"

    def test_resolves_known_aliases(self):
        assert normalize_domain("facebook.com") == "meta.com"
        assert normalize_domain("heroku.com") == "salesforce.com"
        assert normalize_domain("github.com") == "microsoft.com"

    def test_empty_string(self):
        assert normalize_domain("") == ""

    def test_plain_domain(self):
        assert normalize_domain("acme.com") == "acme.com"


class TestDomainsMatch:
    def test_same_domain(self):
        assert domains_match("acme.com", "acme.com")

    def test_www_vs_no_www(self):
        assert domains_match("www.acme.com", "acme.com")

    def test_alias_match(self):
        assert domains_match("facebook.com", "meta.com")

    def test_different_domains(self):
        assert not domains_match("acme.com", "example.com")


class TestCompanyNameSimilarity:
    def test_exact_match(self):
        assert company_names_similar("Acme Inc", "Acme Inc")

    def test_suffix_stripping(self):
        assert company_names_similar("Acme Inc.", "Acme Corporation")

    def test_different_companies(self):
        assert not company_names_similar("Acme Inc", "Globex Corporation")

    def test_case_insensitive(self):
        assert company_names_similar("ACME", "acme")


class TestDeduplicateAccounts:
    def test_dedup_by_domain(self):
        accounts = [
            {"company_name": "Acme", "domain": "acme.com", "industry": "SaaS"},
            {"company_name": "Acme Inc", "domain": "acme.com", "industry": None},
        ]
        result = deduplicate_accounts(accounts)
        assert len(result) == 1
        assert result[0]["company_name"] == "Acme"

    def test_dedup_by_name(self):
        accounts = [
            {"company_name": "Acme Corporation", "domain": None},
            {"company_name": "Acme Corp", "domain": None},
        ]
        result = deduplicate_accounts(accounts)
        assert len(result) == 1

    def test_keeps_different_companies(self):
        accounts = [
            {"company_name": "Acme", "domain": "acme.com"},
            {"company_name": "Globex", "domain": "globex.com"},
        ]
        result = deduplicate_accounts(accounts)
        assert len(result) == 2

    def test_merges_metadata(self):
        accounts = [
            {"company_name": "Acme", "domain": "acme.com", "industry": "SaaS", "revenue": None},
            {"company_name": "Acme", "domain": "acme.com", "industry": None, "revenue": 1000000},
        ]
        result = deduplicate_accounts(accounts)
        assert len(result) == 1
        assert result[0]["industry"] == "SaaS"
        assert result[0]["revenue"] == 1000000


# ---------------------------------------------------------------------------
# Title Normalizer (rule-based)
# ---------------------------------------------------------------------------


class TestTitleNormalizer:
    def test_vp_revops(self):
        result = _rule_based_normalize("VP Revenue Operations")
        assert result["normalized_function"] == "Revenue Operations"
        assert result["normalized_seniority"] == "VP"

    def test_head_of_pricing(self):
        result = _rule_based_normalize("Head of Pricing Strategy")
        assert result["normalized_function"] == "Pricing"
        assert result["normalized_seniority"] == "Director"

    def test_cfo(self):
        result = _rule_based_normalize("CFO")
        assert result["normalized_function"] == "Executive"
        assert result["normalized_seniority"] == "C-Suite"

    def test_senior_engineer(self):
        result = _rule_based_normalize("Senior Billing Engineer")
        assert result["normalized_function"] == "Engineering"
        assert result["normalized_seniority"] == "Senior IC"

    def test_unknown_title(self):
        result = _rule_based_normalize("Astronaut")
        assert result["normalized_function"] == "Other"
        assert result["normalized_seniority"] == "Unknown"

    def test_director_of_finance(self):
        result = _rule_based_normalize("Director of Finance")
        assert result["normalized_function"] == "Finance"
        assert result["normalized_seniority"] == "Director"


# ---------------------------------------------------------------------------
# Contact Linker
# ---------------------------------------------------------------------------


class TestContactLinker:
    def _make_account(self) -> Account:
        return Account(
            id="acc_1",
            workspace_id="ws_1",
            company_name="Acme Corp",
            domain="acme.com",
        )

    def _make_contact(self, email: str = "jane@acme.com", **kwargs) -> Contact:
        defaults = {
            "id": "con_1",
            "workspace_id": "ws_1",
            "account_id": "acc_1",
            "email": email,
        }
        defaults.update(kwargs)
        return Contact(**defaults)

    def test_email_domain_match(self):
        conf = link_confidence(self._make_contact(), self._make_account())
        assert conf >= 0.90

    def test_generic_email_low_confidence(self):
        contact = self._make_contact(email="jane@gmail.com", account_id="acc_other")
        conf = link_confidence(contact, self._make_account())
        assert conf < 0.50

    def test_account_id_match(self):
        contact = self._make_contact(email="jane@other.com")
        conf = link_confidence(contact, self._make_account())
        assert conf >= 0.80  # account_id match

    def test_no_match(self):
        contact = self._make_contact(email="jane@other.com", account_id="acc_other")
        conf = link_confidence(contact, self._make_account())
        assert conf < 0.50

    def test_link_contacts_filters_low_confidence(self):
        account = self._make_account()
        contacts = [
            self._make_contact(email="jane@acme.com"),
            self._make_contact(email="bob@gmail.com", id="con_2", account_id="acc_other"),
        ]
        linked = link_contacts_to_account(contacts, account, min_confidence=0.50)
        assert len(linked) == 1
        assert linked[0][0].email == "jane@acme.com"

    def test_deduplicate_contacts_by_email(self):
        contacts = [
            self._make_contact(email="jane@acme.com", first_name="Jane"),
            self._make_contact(email="jane@acme.com", first_name=None, last_name="Smith", id="con_2"),
        ]
        deduped = deduplicate_contacts(contacts)
        assert len(deduped) == 1
        assert deduped[0].first_name == "Jane"
        assert deduped[0].last_name == "Smith"
