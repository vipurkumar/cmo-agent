"""Canned qualification data for OmniGTM demo mode.

Each company has pre-built responses for every qualification LLM task.
These replace actual Claude API calls during demo mode.
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# Task response maps, keyed by company name (lowercase partial match)
# ---------------------------------------------------------------------------

QUALIFICATION_RESPONSES: dict[str, dict[str, str]] = {
    "novapay": {
        "title_normalization": json.dumps([
            {
                "original_title": "VP Revenue Operations",
                "normalized_function": "revenue_operations",
                "normalized_seniority": "vp",
            },
            {
                "original_title": "Head of Pricing Strategy",
                "normalized_function": "pricing",
                "normalized_seniority": "head",
            },
            {
                "original_title": "Sr. Director, Engineering — Billing & Payments",
                "normalized_function": "engineering",
                "normalized_seniority": "senior_director",
            },
            {
                "original_title": "CFO",
                "normalized_function": "finance",
                "normalized_seniority": "c_level",
            },
            {
                "original_title": "Director of Product, Monetization",
                "normalized_function": "product",
                "normalized_seniority": "director",
            },
        ]),
        "signal_classification": json.dumps([
            {
                "signal_type": "funding",
                "observed_fact": "NovaPay Technologies closed a $58M Series B round led by Tiger Global and Accel India in January 2026, bringing total funding to $81M.",
                "possible_implication": "Fresh capital creates budget for infrastructure investments including monetization tooling. Series C preparation will demand clean revenue recognition and billing accuracy.",
                "confidence": 0.95,
                "reliability_score": 0.97,
            },
            {
                "signal_type": "pricing_change",
                "observed_fact": "NovaPay overhauled their public pricing page in February 2026, adding a new usage-based tier for API calls alongside existing flat-rate plans.",
                "possible_implication": "Transition to hybrid pricing (flat-rate + usage-based) significantly increases billing complexity. Their current Stripe-based setup likely cannot handle metering at API-call granularity without custom engineering.",
                "confidence": 0.88,
                "reliability_score": 0.85,
            },
            {
                "signal_type": "hiring_revops_pricing",
                "observed_fact": "NovaPay posted a Head of Pricing role on LinkedIn on Feb 12, 2026, reporting to the CFO. The JD mentions 'usage-based monetization strategy' and 'billing system evaluation'.",
                "possible_implication": "Active investment in pricing function signals they recognize monetization as a strategic priority. The explicit mention of billing system evaluation suggests they are shopping for solutions.",
                "confidence": 0.91,
                "reliability_score": 0.82,
            },
            {
                "signal_type": "enterprise_motion",
                "observed_fact": "NovaPay launched a dedicated /enterprise page in March 2026 with custom pricing CTAs, SOC 2 badges, and a 'Contact Sales' workflow replacing self-serve signup.",
                "possible_implication": "Enterprise motion introduces CPQ complexity: custom contracts, negotiated pricing, volume discounts. Their existing self-serve billing stack is unlikely to support deal desk workflows.",
                "confidence": 0.84,
                "reliability_score": 0.80,
            },
        ]),
        "account_pain_scoring": json.dumps({
            "pain_fit_score": 82,
            "reasoning": "NovaPay exhibits strong pain signals across multiple dimensions. The combination of a pricing page overhaul introducing usage-based tiers, an active Head of Pricing hire mentioning billing system evaluation, and a new enterprise motion with custom pricing creates a high-urgency, multi-faceted monetization challenge. Their CEO publicly acknowledged billing infrastructure limitations, which is rare and indicates acute internal pressure. The $58M Series B provides budget to act. Score reflects high confidence across 4 converging signals.",
            "evidence": [
                {
                    "statement": "CEO quoted in Economic Times: 'our billing infrastructure can't keep up with usage-based demand'",
                    "evidence_type": "fact",
                    "source": "Economic Times interview, January 2026",
                    "confidence": 0.95,
                },
                {
                    "statement": "Pricing page overhauled to add usage-based API tier alongside flat-rate plans",
                    "evidence_type": "fact",
                    "source": "novapay.com/pricing web archive diff",
                    "confidence": 0.92,
                },
                {
                    "statement": "Head of Pricing job posting mentions 'billing system evaluation' as key responsibility",
                    "evidence_type": "fact",
                    "source": "LinkedIn job posting, Feb 2026",
                    "confidence": 0.88,
                },
                {
                    "statement": "Revenue leakage estimated at 4-6% due to manual reconciliation of usage-based charges",
                    "evidence_type": "inference",
                    "source": "Glassdoor engineering reviews mentioning billing reconciliation issues",
                    "confidence": 0.68,
                },
            ],
            "confidence": 0.85,
        }),
        "pain_inference": json.dumps([
            {
                "pain_type": "pricing_complexity",
                "score": 85,
                "supporting_facts": [
                    {
                        "statement": "Pricing page now shows three models: flat-rate, usage-based per API call, and enterprise custom — all coexisting",
                        "evidence_type": "fact",
                        "source": "novapay.com/pricing",
                        "confidence": 0.92,
                    },
                    {
                        "statement": "CEO publicly stated billing infrastructure is a bottleneck for growth",
                        "evidence_type": "fact",
                        "source": "Economic Times interview",
                        "confidence": 0.95,
                    },
                ],
                "inferences": [
                    "Managing three concurrent pricing models (flat, usage, custom) with 40+ fintech partners creates combinatorial billing complexity",
                    "The CEO's public admission suggests internal escalation has already happened — this is not a future problem, it is a current crisis",
                    "Engineering team is likely spending significant sprint capacity on billing edge cases instead of core product development",
                ],
                "unknowns": [
                    "Exact scope of current billing system — Stripe alone or Stripe + custom code",
                    "Whether they have evaluated other billing platforms already",
                ],
                "confidence_score": 0.87,
            },
            {
                "pain_type": "expansion_pricing",
                "score": 72,
                "supporting_facts": [
                    {
                        "statement": "NovaPay processes $2.1B in annualized transaction volume across 40+ fintech partners with varying usage tiers",
                        "evidence_type": "fact",
                        "source": "Company press release",
                        "confidence": 0.90,
                    },
                    {
                        "statement": "Enterprise page launched with custom pricing CTAs, suggesting negotiated contracts",
                        "evidence_type": "fact",
                        "source": "novapay.com/enterprise",
                        "confidence": 0.85,
                    },
                ],
                "inferences": [
                    "With 40+ partners on different pricing tiers, expansion and upsell pricing likely requires manual intervention for each account",
                    "Enterprise custom contracts will need a deal desk or CPQ workflow that does not exist today",
                ],
                "unknowns": [
                    "Current expansion revenue as a percentage of total ARR",
                    "Whether they have a deal desk team or if sales handles pricing ad hoc",
                ],
                "confidence_score": 0.74,
            },
            {
                "pain_type": "quote_to_cash_friction",
                "score": 65,
                "supporting_facts": [
                    {
                        "statement": "Enterprise page uses 'Contact Sales' flow rather than self-serve, implying manual quoting",
                        "evidence_type": "fact",
                        "source": "novapay.com/enterprise",
                        "confidence": 0.82,
                    },
                ],
                "inferences": [
                    "Transition from PLG to enterprise sales motion creates a gap between quoting and billing systems",
                    "Manual reconciliation of usage-based charges likely causes invoicing delays and disputes with larger partners",
                ],
                "unknowns": [
                    "Average time from quote to first invoice for enterprise deals",
                    "Whether finance team is manually reconciling usage charges",
                    "Dispute rate on invoices",
                ],
                "confidence_score": 0.62,
            },
        ]),
        "contact_ranking": json.dumps([
            {
                "contact_id": "np-contact-001",
                "name": "Sarah Chen",
                "title": "VP Revenue Operations",
                "normalized_function": "revenue_operations",
                "normalized_seniority": "vp",
                "relevance_score": 94,
                "likely_role": "pain_owner",
                "reason_for_relevance": "As VP RevOps, Sarah owns the revenue infrastructure stack including billing, pricing systems, and CRM. She directly feels the pain of manual reconciliation, revenue leakage, and billing complexity across 40+ partners. Her team is the primary stakeholder for any monetization platform investment.",
                "confidence_score": 0.91,
            },
            {
                "contact_id": "np-contact-002",
                "name": "Marcus Johnson",
                "title": "Head of Pricing Strategy",
                "normalized_function": "pricing",
                "normalized_seniority": "head",
                "relevance_score": 88,
                "likely_role": "economic_buyer",
                "reason_for_relevance": "Newly hired to own pricing strategy and evaluate billing systems per the job description. Marcus will likely drive vendor selection for any pricing and billing platform. His mandate to build out usage-based monetization strategy directly aligns with Monetize360's core capabilities.",
                "confidence_score": 0.85,
            },
            {
                "contact_id": "np-contact-003",
                "name": "Raj Patel",
                "title": "Sr. Director, Engineering — Billing & Payments",
                "normalized_function": "engineering",
                "normalized_seniority": "senior_director",
                "relevance_score": 73,
                "likely_role": "technical_evaluator",
                "reason_for_relevance": "Raj leads the engineering team responsible for billing infrastructure. His team bears the cost of maintaining custom billing code and handling edge cases. He will evaluate technical fit, API capabilities, and integration complexity of any new platform.",
                "confidence_score": 0.78,
            },
        ]),
        "value_prop_matching": json.dumps([
            {
                "contact_id": "np-contact-001",
                "top_problem": "Revenue operations team spending 30%+ of capacity on manual billing reconciliation and usage-based metering edge cases instead of strategic work",
                "relevant_capability": "Automated usage-based metering and real-time revenue recognition with no-code configuration for hybrid pricing models",
                "expected_business_outcome": "Eliminate 4-6% revenue leakage and reclaim 30% of RevOps engineering bandwidth within 6 weeks of deployment",
                "one_line_hook": "Acme SaaS cut deal desk cycle time by 52% — NovaPay's billing complexity is 3x theirs and you're scaling faster.",
                "short_value_prop": "Monetize360 handles flat-rate, usage-based, and enterprise custom pricing natively — no engineering sprints required. Our platform meters API calls at the granularity NovaPay needs, reconciles in real time, and generates audit-ready revenue recognition reports for your Series C prep.",
                "likely_objection": "We've already invested heavily in custom billing code on top of Stripe. Switching costs feel high.",
                "suggested_response": "That's exactly why our customers come to us — not to rip out Stripe, but to layer Monetize360 on top. We integrate with your existing Stripe setup, handle the metering and reconciliation logic, and your engineering team stops maintaining billing edge cases. FinTech Co did the same migration in 4 weeks.",
                "confidence_score": 0.89,
            },
            {
                "contact_id": "np-contact-002",
                "top_problem": "Building a usage-based monetization strategy without infrastructure that can actually execute it — forced to compromise pricing design around billing system limitations",
                "relevant_capability": "No-code pricing model configuration supporting usage-based, tiered, hybrid, and custom enterprise models with real-time experimentation",
                "expected_business_outcome": "Launch new pricing tiers in days instead of engineering sprints, with built-in A/B testing to optimize conversion and expansion revenue",
                "one_line_hook": "Your JD says 'billing system evaluation' — here's what FinTech Co found when they evaluated us: 31% shorter sales cycles from day one.",
                "short_value_prop": "Monetize360 lets you design the pricing model first and worry about billing execution never. Configure usage-based, tiered, and enterprise custom pricing in our no-code builder. Your engineering team ships product while we handle metering, invoicing, and revenue recognition.",
                "likely_objection": "I just started this role — I need to understand the landscape before evaluating vendors.",
                "suggested_response": "Completely understand. Most Heads of Pricing we work with start with a 20-minute landscape briefing where we share what we're seeing across 200+ B2B companies on pricing model transitions. No pitch — just context that helps you build your strategy. Would that be useful?",
                "confidence_score": 0.83,
            },
            {
                "contact_id": "np-contact-003",
                "top_problem": "Engineering team trapped in a cycle of billing edge case fixes, spending 30% of sprints on metering and reconciliation bugs instead of building core BaaS product features",
                "relevant_capability": "API-first billing platform with pre-built metering SDKs, webhook-based event ingestion, and automated reconciliation that replaces custom billing code",
                "expected_business_outcome": "Reclaim 30% of engineering sprint capacity currently consumed by billing maintenance and eliminate the queue of 47 open billing-related Jira tickets",
                "one_line_hook": "Your team is building billing infrastructure that isn't your product. What if you could delete 10,000 lines of billing code and ship BaaS features instead?",
                "short_value_prop": "Monetize360's metering SDK drops into your existing Python/Kafka stack with a 3-day integration. We handle API-call-level usage tracking, automated reconciliation, and invoice generation. Your engineering team goes from billing firefighters to product builders.",
                "likely_objection": "Another third-party dependency in our billing stack adds risk, not reduces it.",
                "suggested_response": "Fair concern. Our architecture is designed for exactly this: we run alongside your existing stack with a fallback mode, so if our service has issues, your billing doesn't stop. We also provide full audit logs and real-time monitoring. Happy to walk through our SLA and architecture with your team.",
                "confidence_score": 0.79,
            },
        ]),
        "brief_generation": json.dumps({
            "account_snapshot": "NovaPay Technologies is a Series B embedded finance platform ($58M raised, $85M revenue, 450 employees) processing $2.1B in annualized transaction volume across 40+ fintech partners. Headquartered in Bangalore with US offices. They provide Banking-as-a-Service APIs enabling fintechs and neobanks to embed payments, lending, and card issuance. Currently transitioning from flat-rate to hybrid pricing (flat + usage-based + enterprise custom) while preparing for a Series C raise.",
            "why_this_account": "NovaPay is a near-perfect ICP match: B2B SaaS in fintech, right size band (450 employees, $85M revenue), usage-based pricing complexity, and active billing infrastructure pain. Four converging signals — Series B funding, pricing page overhaul, Head of Pricing hire, and enterprise page launch — indicate both urgency and budget. The CEO's public acknowledgment of billing limitations is rare executive-level validation of the pain. Three well-mapped buying committee members with clear roles reduce engagement risk.",
            "why_now": "Three timing factors create a narrow window of opportunity: (1) The Head of Pricing role was posted 5 weeks ago — Marcus Johnson is likely in his first 90 days and actively building his vendor landscape. (2) The enterprise page launched in March 2026, meaning enterprise deal flow is starting now and will expose CPQ gaps within the quarter. (3) Series C preparation typically begins 12-18 months after Series B — revenue recognition and billing accuracy will become board-level priorities by Q3 2026.",
            "risks_and_unknowns": [
                "Unknown whether NovaPay has already engaged with competitors like Zuora, Chargebee, or Maxio for billing platform evaluation",
                "Raj Patel's engineering team may have internal momentum behind a build-not-buy approach given their existing custom billing code",
                "APAC-first company may have procurement cycles and compliance requirements unfamiliar to our sales team",
                "The Head of Pricing role may still be unfilled — Marcus Johnson's start date is not confirmed",
                "Revenue leakage estimate (4-6%) is inferred from Glassdoor reviews, not confirmed by the company",
            ],
        }),
    },
    "medicloud": {
        "title_normalization": json.dumps([
            {
                "original_title": "VP Clinical Operations",
                "normalized_function": "operations",
                "normalized_seniority": "vp",
            },
            {
                "original_title": "Director, Business Development & Partnerships",
                "normalized_function": "business_development",
                "normalized_seniority": "director",
            },
        ]),
        "signal_classification": json.dumps([
            {
                "signal_type": "new_product_launch",
                "observed_fact": "MediCloud AI received FDA clearance for their AI pathology module covering 12 cancer types in December 2025. The clearance enables clinical deployment at scale across their 150+ hospital partners.",
                "possible_implication": "FDA clearance accelerates enterprise adoption and volume growth, which will increase billing complexity. However, this is primarily a product milestone, not a direct pricing or billing signal. The connection to monetization pain is indirect.",
                "confidence": 0.78,
                "reliability_score": 0.92,
            },
            {
                "signal_type": "pricing_change",
                "observed_fact": "MediCloud announced an outcome-based pricing pilot where hospitals pay per accurate diagnosis rather than per-seat or per-inference. The pilot covers 8 hospital systems.",
                "possible_implication": "Outcome-based pricing is highly complex to meter and bill — it requires linking clinical outcomes to billing events. However, this is a small pilot (8 hospitals) and may not expand. The pricing model is experimental and may be abandoned.",
                "confidence": 0.65,
                "reliability_score": 0.70,
            },
        ]),
        "account_pain_scoring": json.dumps({
            "pain_fit_score": 48,
            "reasoning": "MediCloud AI shows moderate pain signals but with significant uncertainty. The outcome-based pricing pilot is innovative but limited to 8 hospitals, suggesting it is experimental rather than a committed strategic direction. Their core business (per-seat + per-inference) is a relatively standard hybrid model that many billing platforms handle adequately. The FDA clearance is a positive company milestone but does not directly indicate billing infrastructure pain. The company's smaller size (150 employees, $22M revenue) and healthtech focus place them at the edge of our ICP. Pain exists but is not acute or broadly felt across the organization yet.",
            "evidence": [
                {
                    "statement": "Outcome-based pricing pilot is limited to 8 hospital systems out of 150+ partners",
                    "evidence_type": "fact",
                    "source": "MediCloud press release, Q4 2025",
                    "confidence": 0.82,
                },
                {
                    "statement": "Core pricing model (per-seat + per-inference) is standard SaaS hybrid, not highly complex",
                    "evidence_type": "inference",
                    "source": "medicloud.ai/pricing analysis",
                    "confidence": 0.72,
                },
            ],
            "confidence": 0.58,
        }),
        "pain_inference": json.dumps([
            {
                "pain_type": "billing_mismatch",
                "score": 55,
                "supporting_facts": [
                    {
                        "statement": "Finance team manually calculating invoices for top 30 hospital accounts using spreadsheets",
                        "evidence_type": "inference",
                        "source": "Glassdoor reviews from finance team members",
                        "confidence": 0.55,
                    },
                    {
                        "statement": "Outcome-based pricing pilot requires linking clinical diagnostic accuracy to billing events — no standard billing platform supports this natively",
                        "evidence_type": "fact",
                        "source": "MediCloud pricing announcement",
                        "confidence": 0.70,
                    },
                ],
                "inferences": [
                    "The outcome-based pricing model will require custom metering infrastructure if the pilot expands beyond 8 hospitals",
                    "HIPAA compliance requirements add a layer of complexity to any billing data flow changes",
                ],
                "unknowns": [
                    "Whether the outcome-based pricing pilot will expand or be abandoned",
                    "Current billing system and whether they have evaluated replacements",
                    "Whether the finance team's manual invoicing is seen as a problem by leadership or accepted as status quo",
                    "Budget allocation for billing infrastructure vs. R&D and clinical AI development",
                    "Timeline for scaling beyond current 150+ hospital partners",
                ],
                "confidence_score": 0.52,
            },
        ]),
        "contact_ranking": json.dumps([
            {
                "contact_id": "mc-contact-001",
                "name": "Dr. Anita Sharma",
                "title": "VP Clinical Operations",
                "normalized_function": "operations",
                "normalized_seniority": "vp",
                "relevance_score": 52,
                "likely_role": "unknown",
                "reason_for_relevance": "As VP Clinical Operations, Dr. Sharma oversees the hospital partner relationships and clinical deployment workflows. She may have visibility into billing and invoicing friction, but her primary focus is clinical operations, not revenue infrastructure. Connection to monetization pain is indirect at best.",
                "confidence_score": 0.48,
            },
            {
                "contact_id": "mc-contact-002",
                "name": "David Park",
                "title": "Director, Business Development & Partnerships",
                "normalized_function": "business_development",
                "normalized_seniority": "director",
                "relevance_score": 45,
                "likely_role": "unknown",
                "reason_for_relevance": "David manages hospital partnerships and pricing negotiations. He likely encounters friction in the quoting process for outcome-based pricing but is not the budget owner for billing infrastructure. His perspective would be valuable for understanding deal complexity but he is unlikely to champion a billing platform purchase.",
                "confidence_score": 0.42,
            },
        ]),
        "value_prop_matching": json.dumps([
            {
                "contact_id": "mc-contact-001",
                "top_problem": "Outcome-based pricing pilot creates invoicing complexity that the finance team handles manually, risking errors and scalability issues if the pilot expands",
                "relevant_capability": "Flexible billing models supporting usage-based, outcome-driven, and hybrid pricing with automated invoicing and revenue recognition",
                "expected_business_outcome": "Automate invoicing for outcome-based pricing pilot, reducing manual calculation effort and enabling confident expansion to additional hospital partners",
                "one_line_hook": "Your outcome-based pricing pilot is innovative — but can your billing system actually scale it beyond 8 hospitals?",
                "short_value_prop": "Monetize360 can meter outcome-based billing events and automate the invoicing workflow your finance team currently handles in spreadsheets. If the pilot succeeds and you need to scale to 50 or 100 hospitals, the billing infrastructure needs to be ready before the partnerships are.",
                "likely_objection": "We're a 150-person healthtech company focused on clinical AI. Billing infrastructure is not our top priority right now — FDA clearance and clinical adoption are.",
                "suggested_response": "That makes sense, and we would not suggest this is your top priority today. What we've seen with similar companies is that billing becomes a blocker exactly when clinical adoption accelerates — and by then it's too late to implement a clean solution. A 15-minute conversation now could save a fire drill in 6 months.",
                "confidence_score": 0.55,
            },
            {
                "contact_id": "mc-contact-002",
                "top_problem": "Pricing negotiations with hospital partners lack tooling support, making each custom deal a manual spreadsheet exercise",
                "relevant_capability": "Deal desk automation with configurable pricing rules, approval workflows, and automated contract-to-invoice flow",
                "expected_business_outcome": "Reduce pricing negotiation cycle time and eliminate manual invoice calculation for custom hospital contracts",
                "one_line_hook": "Every hospital deal is a custom spreadsheet today. That won't work at 300 hospitals.",
                "short_value_prop": "Monetize360 automates the quote-to-invoice workflow so your partnerships team can negotiate pricing models confidently, knowing the billing system will execute whatever they agree to — per-seat, per-inference, outcome-based, or any combination.",
                "likely_objection": "We only have 150 hospital partners. The volume doesn't justify a platform investment yet.",
                "suggested_response": "Understood. Most of our customers felt the same way at your stage. We offer a lightweight pilot that covers your top 30 accounts — the ones your finance team invoices manually today. If it saves 20 hours a month, the ROI is immediate. No commitment to a full rollout until you're ready.",
                "confidence_score": 0.48,
            },
        ]),
        "brief_generation": json.dumps({
            "account_snapshot": "MediCloud AI is a healthtech company ($22M revenue, 150 employees) providing AI-powered clinical decision support to 150+ hospitals. Recently received FDA clearance for an AI pathology module and launched an outcome-based pricing pilot with 8 hospital systems. Funded by GV and Khosla Ventures ($35M Series A extension). Core pricing is per-seat + per-inference hybrid with an experimental outcome-based tier.",
            "why_this_account": "MediCloud has moderate ICP fit: healthtech is adjacent to our core SaaS/fintech focus, and at 150 employees and $22M revenue they are at the lower end of our target range. The outcome-based pricing pilot is genuinely innovative and represents a billing challenge that few platforms can solve. However, this is an early-stage experiment (8 hospitals), and the core business uses standard hybrid pricing that is not particularly complex. The buying committee is thin — we identified only 2 contacts with indirect relevance to billing infrastructure decisions.",
            "why_now": "The timing case is moderate. The FDA clearance could accelerate hospital adoption, which would eventually strain billing infrastructure — but that strain is 6-12 months away. The outcome-based pricing pilot is interesting but may not expand. There is no active hiring signal for pricing or RevOps roles, and no public indication that billing infrastructure is a recognized pain point at the leadership level. The Series A extension provides some budget, but R&D and clinical AI development are likely higher priorities.",
            "risks_and_unknowns": [
                "Outcome-based pricing pilot may be abandoned if clinical outcomes prove difficult to standardize for billing purposes",
                "No VP Finance, Head of Pricing, or RevOps leader identified — unclear who would champion a billing platform purchase",
                "Healthtech procurement cycles are long and compliance-heavy, with HIPAA adding 4-8 weeks to typical vendor evaluation",
                "Company may view billing as a solved problem at current scale and not prioritize infrastructure investment until forced",
                "Our case studies and proof points are from SaaS and fintech — healthcare-specific references are limited",
                "Budget allocation is likely weighted heavily toward R&D and clinical AI, leaving limited discretionary spend for operations tooling",
            ],
        }),
    },
}


def get_demo_qualification_response(task: str, prompt_text: str) -> str | None:
    """Return canned response for a qualification task based on company name in prompt.

    Performs a case-insensitive partial match against known demo company keys.
    Returns the pre-built JSON string for the matching task, or None if no
    company match is found or the task is not recognized.
    """
    prompt_lower = prompt_text.lower()
    for company_key, responses in QUALIFICATION_RESPONSES.items():
        if company_key in prompt_lower:
            return responses.get(task)
    return None
