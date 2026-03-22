"""Demo call_claude() — returns realistic canned responses for Monetize360 GTM demo."""

from __future__ import annotations

import json
import re

from src.logger import log

# Per-company research & email data so each account feels unique
_COMPANY_DATA = {
    "NovaPay Technologies": {
        "summary": (
            "NovaPay Technologies is a Series B embedded finance platform with 420 employees, "
            "headquartered in Bangalore with US offices. They offer Banking-as-a-Service APIs "
            "enabling fintechs and neobanks to embed payments, lending, and card issuance. "
            "Processing $2.1B in annualized transaction volume across 40+ fintech partners. "
            "Recently launched a usage-based pricing tier for their API suite but struggling "
            "with billing accuracy at scale."
        ),
        "recent_news": [
            "NovaPay raised $58M Series B led by Tiger Global and Accel India",
            "Launched embedded lending APIs for BNPL providers across Southeast Asia",
            "CEO quoted in ET saying 'our billing infrastructure can't keep up with usage-based demand'",
        ],
        "pain_points": [
            "Current billing system can't handle usage-based metering at API-call granularity",
            "Revenue leakage estimated at 4-6% due to manual reconciliation gaps",
            "Engineering team spending 30% of sprints on billing edge cases instead of core product",
            "Need real-time revenue recognition for Series C readiness",
        ],
        "personalization_hooks": [
            "CEO publicly admitted billing infrastructure is a bottleneck — rare candor, high urgency",
            "Series B gives budget to invest in monetization infrastructure now",
            "Usage-based API pricing is exactly the complexity MTZ360 was built for",
            "40+ fintech partners means multi-tenant billing complexity — our sweet spot",
        ],
        "technologies": ["Python", "AWS", "Kubernetes", "PostgreSQL", "Kafka", "Stripe (outgrowing)"],
        "email_subject": "Fixing usage-based billing at NovaPay's scale",
        "email_body": (
            "Hi Ravi,\n\n"
            "Congrats on the Series B — $58M is serious momentum. I noticed your "
            "CEO's comment in ET about billing infrastructure not keeping up with "
            "usage-based demand. That's a problem we know well.\n\n"
            "We're Monetize360 — our no-code platform MTZ360 handles exactly this: "
            "usage-based, tiered, and hybrid pricing models at API-call granularity, "
            "without your engineering team having to build and maintain it.\n\n"
            "One of our fintech clients cut their billing ops overhead by 70% and "
            "eliminated revenue leakage within 6 weeks of going live.\n\n"
            "Given where NovaPay is headed with 40+ partners and a Series C on the "
            "horizon, might be worth a 15-min look at how MTZ360 could free up your "
            "engineering team. Open to a quick call next week?\n\n"
            "Best,\nMonetize360 GTM Team"
        ),
    },
    "MediCloud AI": {
        "summary": (
            "MediCloud AI is a healthcare IT company with 280 employees providing an "
            "AI-powered clinical decision support platform used by 150+ hospitals and "
            "health systems. Their platform runs diagnostic AI models on medical imaging "
            "and EHR data, charged on a per-inference and per-seat hybrid model. "
            "Recently expanded into AI-assisted pathology with outcome-based pricing "
            "but lacking infrastructure to meter and bill for it."
        ),
        "recent_news": [
            "MediCloud AI closed $35M Series A extension from GV and Khosla Ventures",
            "FDA cleared their AI pathology module for clinical use in 12 cancer types",
            "Announced outcome-based pricing pilot — hospitals pay per accurate diagnosis",
        ],
        "pain_points": [
            "No billing system that supports outcome-based pricing tied to clinical results",
            "Hybrid model (per-seat + per-inference + outcome-based) creates invoicing nightmares",
            "HIPAA compliance adds complexity to metering and billing data flows",
            "Finance team manually calculating invoices for top 30 hospital accounts",
        ],
        "personalization_hooks": [
            "Outcome-based pricing in healthcare is cutting-edge — MTZ360 can meter outcomes natively",
            "FDA clearance accelerates enterprise adoption, making billing scalability urgent now",
            "HIPAA-compliant billing automation is a differentiator we can deliver",
            "Series A extension signals they're investing in scaling operations, not just R&D",
        ],
        "technologies": ["Python", "GCP", "FHIR APIs", "TensorFlow", "BigQuery", "Custom invoicing scripts"],
        "email_subject": "Outcome-based billing for MediCloud's new pricing model",
        "email_body": (
            "Hi Lisa,\n\n"
            "Really impressive work getting FDA clearance for the AI pathology module "
            "— 12 cancer types is a major clinical milestone.\n\n"
            "I noticed MediCloud just announced an outcome-based pricing pilot where "
            "hospitals pay per accurate diagnosis. That's a bold move, and exactly the "
            "kind of complex billing model that breaks most platforms.\n\n"
            "We're Monetize360 — our platform MTZ360 handles usage-based, hybrid, and "
            "outcome-driven pricing natively, no code required. We already work with "
            "healthcare companies that need HIPAA-aware billing pipelines.\n\n"
            "With 150+ hospitals and three different pricing tiers, I imagine the "
            "invoicing complexity is growing fast. Would a 20-min call make sense to "
            "explore how MTZ360 could automate this?\n\n"
            "Best,\nMonetize360 GTM Team"
        ),
    },
}

_DEFAULT_DATA = {
    "summary": "Enterprise company with complex billing needs and growing revenue operations challenges.",
    "recent_news": ["Recent funding round announced", "New product launch with usage-based pricing"],
    "pain_points": ["Manual billing processes", "Revenue leakage from metering gaps", "Engineering time spent on billing"],
    "personalization_hooks": ["Growing billing complexity signals need for monetization platform"],
    "technologies": ["Python", "AWS", "PostgreSQL"],
    "email_subject": "Simplifying your billing complexity",
    "email_body": "Hi,\n\nWe help companies automate complex billing. Would love to chat.\n\nBest,\nMonetize360 GTM Team",
}


async def demo_call_claude(
    task: str,
    system: str | list[dict],
    user: str,
    workspace_id: str,
    model: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """Drop-in replacement for budget.call_claude() in demo mode."""
    log.info("demo.call_claude", task=task, workspace_id=workspace_id, model=model)

    company = _extract_company(user)
    log.info("demo.call_claude.extracted_company", company=company)
    data = _COMPANY_DATA.get(company, _DEFAULT_DATA)

    responses: dict[str, str] = {
        "research": json.dumps({
            "company_summary": data["summary"],
            "recent_news": data["recent_news"],
            "pain_points": data["pain_points"],
            "personalization_hooks": data["personalization_hooks"],
            "technologies": data["technologies"],
        }),
        "email_generation": json.dumps({
            "subject": data.get("email_subject", f"Quick thought on {company}'s billing"),
            "body": data.get("email_body", _DEFAULT_DATA["email_body"]),
            "personalization_score": 0.91,
        }),
        "reply_analysis": json.dumps({
            "intent": "positive",
            "confidence": 0.94,
            "reasoning": (
                "The reply expresses strong interest in learning more about automating "
                "their billing infrastructure. They propose a specific time for a call "
                "and mention internal urgency around their pricing model transition."
            ),
            "suggested_action": "notify_sales",
        }),
        "classification": json.dumps({
            "category": "interested",
            "confidence": 0.91,
        }),
        "personalization": json.dumps({
            "subject": f"Re: {company}'s monetization infrastructure",
            "body": f"Following up on billing automation for {company}...",
        }),
        "summarization": json.dumps({
            "summary": f"Key findings about {company}: complex billing needs, growing revenue ops challenges, strong fit for MTZ360.",
        }),
    }

    result = responses.get(task, json.dumps({"result": f"Demo response for task: {task}"}))
    log.info("demo.call_claude.complete", task=task, workspace_id=workspace_id)
    return result


def _extract_company(text: str) -> str:
    """Best-effort extraction of a company name from prompt text."""
    # Check for known demo companies by keyword first (most reliable)
    for company in ("NovaPay Technologies", "MediCloud AI"):
        if company in text:
            return company
    # Try structured formats
    match = re.search(r"(?:Company|Name|company_name)[\"'\s:]+\s*(.+?)(?:\n|\"|,|$)", text)
    if match:
        name = match.group(1).strip().strip('"').strip("'")
        if name:
            return name
    return "NovaPay Technologies"
