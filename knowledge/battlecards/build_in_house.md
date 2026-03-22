# Competitive Battlecard: Build In-House

## When You'll Encounter "Build In-House"

The build-in-house objection surfaces when:

- The prospect has a strong engineering culture and defaults to building over buying (common at developer-tools companies, infrastructure companies, and engineering-led organizations).
- A senior engineering leader (VP Eng, CTO) is involved in the evaluation and sees billing/pricing as a core competency.
- The prospect has already built a basic billing system and is considering extending it rather than replacing it.
- The prospect has had bad experiences with third-party billing vendors in the past (poor support, forced migrations, unexpected pricing changes).
- The prospect perceives their billing model as too unique for any vendor to handle.

This is one of the most common competitive scenarios — and one of the most winnable. The decision to build in-house is almost always based on underestimating the long-term cost and overestimating the uniqueness of the billing problem.

## Key Stats: The Real Cost of Building In-House

These numbers come from aggregated customer interviews and industry benchmarks. Use them in conversations, adjusted for the prospect's team size and billing complexity.

| Metric | Build In-House | OmniGTM |
|---|---|---|
| **Initial build time** | 12-18 engineer-months for V1 | 5-10 weeks to full production |
| **Initial build cost** | $1.2M-$1.8M (fully loaded eng cost at $120K-$150K/yr per engineer) | Subscription pricing — fraction of build cost |
| **Ongoing maintenance** | 2-3 engineers dedicated (20-30% of their time minimum) | Included in subscription |
| **3-year TCO** | 60% higher than vendor solution on average | Predictable subscription cost |
| **Time to new pricing model** | 6-12 weeks of engineering work | Configuration change, live in days |
| **Compliance updates** | Manual tracking and implementation | Automated, included |
| **Revenue leakage risk** | 2-5% of revenue in billing errors (industry average for homegrown systems) | < 0.5% with automated validation |
| **Opportunity cost** | 12-18 months of engineering time not spent on core product | Zero engineering distraction |

## Common Objections and Responses

### "We know our business better than any vendor."

**Response**: "You absolutely know your business better than we do — and you should. The question is whether billing and pricing infrastructure is your business, or a tool your business needs. You know your customers, your market, and your product better than anyone. But the mechanics of usage metering, multi-currency settlement, ASC 606 revenue recognition, and entitlement management — those are hard engineering problems that are the same across every B2B company. We've solved them thousands of times. Your engineers' time is better spent on the things only they can build — your core product. DataFlow Analytics had 2 engineers maintaining their billing system full-time. After migrating to OmniGTM, those engineers shipped 3 product features in the first quarter that had been stuck in the backlog for 18 months."

### "We have security and data concerns with third-party billing."

**Response**: "That's a legitimate concern and one we take seriously. Let me address it directly: OmniGTM is SOC 2 Type II certified, GDPR compliant, and for healthcare customers, HIPAA compliant with signed BAAs. All billing data is encrypted at rest and in transit. We support data residency requirements for EU, APAC, and other regulated regions. MediBill Pro — a healthcare billing company with HIPAA requirements — deployed OmniGTM and has had zero billing-related compliance incidents in 12 months. What specific security or data requirements are driving the concern? I'd rather address them concretely than in the abstract."

### "We already built a billing system — why not just extend it?"

**Response**: "Extending an existing system feels cheaper than replacing it, but the economics usually don't hold up. The first 80% of a billing system — basic invoicing, simple subscription management — is straightforward. The next 20% — usage-based rating, multi-currency, revenue recognition, entitlement management, edge cases — is where 80% of the engineering time goes. Every customer who's come to us from a homegrown system tells the same story: V1 took 6 months and worked fine. Then they spent the next 2 years patching edge cases, handling compliance changes, and debugging billing errors that were costing them real revenue. DataFlow Analytics was leaking $340K annually in billing errors from their homegrown system before they migrated. What's the current error rate on your billing, and how much engineering time goes into maintaining what you've built?"

### "We have the engineers available."

**Response**: "Having available engineers is a great problem to have. The question is what's the highest-value use of their time. Let me put some numbers on it: building a billing system that handles usage-based pricing, multi-currency, compliance, and revenue recognition takes 12-18 engineer-months for V1, plus 2-3 engineers on ongoing maintenance. At a fully loaded cost of $130K per engineer per year, that's $1.5M+ in the first year alone, before you account for opportunity cost. CloudShift.io's VP of Sales told us that the 23% increase in deal size from OmniGTM's CPQ — $1.8M in annual margin improvement — would have taken their engineering team 2+ years to build, if they ever got to it. What features are on your product roadmap that those engineers could be working on instead?"

### "Vendor lock-in concerns."

**Response**: "Vendor lock-in is a real risk with any third-party system, and I won't pretend otherwise. Here's how we mitigate it: OmniGTM exposes all your billing data through open APIs with full export capability. Your pricing models, customer records, transaction history, and entitlement configurations are all exportable in standard formats at any time. We don't hold your data hostage. That said, let me flip the question: building in-house creates its own lock-in — to the engineers who built it, to the architecture decisions they made, and to the maintenance burden that grows every year. At least with a vendor, you can switch. With a homegrown system, you're locked in to your own technical debt."

## Win Themes Against Build In-House

1. **Opportunity cost is the real cost**: The $1.5M+ in direct build costs is only half the story. The real cost is what those engineers don't build while they're maintaining billing infrastructure. Every quarter spent on billing is a quarter not spent on core product features that drive revenue.

2. **The 80/20 trap**: The first 80% of a billing system is easy. The last 20% — edge cases, compliance, multi-currency, revenue recognition — takes 80% of the total effort and is where homegrown systems create the most risk. Companies consistently underestimate this long tail.

3. **Maintenance never ends**: Building V1 is a project. Maintaining a billing system is a permanent commitment. Tax law changes, compliance updates, new currency support, ASC 606 amendments — these are ongoing costs that compound year over year. OmniGTM handles all of this as part of the subscription.

4. **Revenue leakage is invisible**: Homegrown billing systems average 2-5% revenue leakage from billing errors, missed overages, and incorrect entitlements. This is money that never shows up as a line item because you don't know it's missing. DataFlow Analytics discovered $340K in annual leakage only after deploying OmniGTM's automated validation.

5. **Speed to market**: When your pricing strategy needs to change — new tier, new usage model, new market — OmniGTM makes it a configuration change. With a homegrown system, it's a feature request in the engineering backlog competing with product priorities. PayStream Global launched 12 new markets in 6 months; with a homegrown system, they projected 18 months for 15 markets.

## Case Study References

- **DataFlow Analytics**: 2 FTEs freed from billing maintenance, $340K in revenue leakage eliminated, $2.1M annual savings.
- **CloudShift.io**: 23% increase in deal size from CPQ that would have taken 2+ years to build internally.
- **PayStream Global**: 12 new markets in 6 months vs 18-month projection with internal tooling.
- **MediBill Pro**: 90% automated rev rec for outcome-based billing — a model that homegrown systems almost never handle correctly.

## Discovery Questions for Build-In-House Prospects

- "How many engineer-months have you spent on your current billing system, including ongoing maintenance?"
- "When was the last time you needed to change your pricing model, and how long did the engineering work take?"
- "What's your current billing error rate, and how do you measure it?"
- "How many engineers are currently spending part of their time maintaining billing infrastructure vs working on core product?"
- "If you could free up the engineers currently maintaining billing, what would they work on?"
- "How are you handling revenue recognition compliance today — ASC 606 specifically? Is that automated or manual?"
