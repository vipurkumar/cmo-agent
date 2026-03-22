"""Default Ideal Customer Profile criteria and scoring weights for OmniGTM.

Weights determine the relative importance of each scoring dimension.
All weights must sum to 1.0 within their category.
"""

from __future__ import annotations

# --- ICP Scoring Weights ---
# Each weight controls the contribution to icp_fit_score (0–100)

ICP_WEIGHTS = {
    "industry": 0.15,
    "business_model": 0.10,
    "company_size": 0.10,
    "revenue": 0.10,
    "geography": 0.05,
    "growth_stage": 0.10,
    "monetization_complexity": 0.15,
    "pricing_maturity": 0.10,
    "enterprise_sales_motion": 0.10,
    "historical_similarity": 0.05,
}

# --- Default ICP Criteria ---

DEFAULT_ICP = {
    "company_size": {"min": 50, "max": 5000},
    "revenue_range": {"min": 5_000_000, "max": 500_000_000},
    "industries": [
        "SaaS",
        "B2B Software",
        "Cloud Infrastructure",
        "DevTools",
        "FinTech",
        "HealthTech",
        "MarTech",
        "Data & Analytics",
    ],
    "business_models": [
        "subscription",
        "usage_based",
        "hybrid",
        "marketplace",
        "platform",
    ],
    "geographies": ["US", "UK", "DE", "NL", "FR", "CA", "AU"],
    "roles_to_target": [
        "VP Revenue Operations",
        "Head of Pricing",
        "VP Finance",
        "CFO",
        "Head of Growth",
        "VP Product",
        "Director of Billing",
        "Head of Monetization",
    ],
    "technologies": [
        "stripe",
        "chargebee",
        "zuora",
        "recurly",
        "maxio",
        "salesforce_cpq",
    ],
    "monetization_signals": [
        "multiple_pricing_tiers",
        "usage_based_component",
        "enterprise_custom_pricing",
        "freemium_model",
        "hybrid_pricing",
    ],
    "negative_signals": [
        "hiring_freeze",
        "recent_layoffs",
        "bankruptcy",
        "pre_revenue",
        "acquired_recently",
    ],
    "positive_signals": [
        "recent_funding",
        "new_c_level_hire",
        "expansion",
        "product_launch",
        "pricing_page_change",
        "hiring_revops",
        "hiring_pricing",
        "enterprise_launch",
    ],
    "disqualify_rules": [
        "employee_count_below_20",
        "no_saas_model",
        "direct_competitor",
        "existing_customer",
    ],
}
