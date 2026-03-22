# Case Study: MediBill Pro

## Company Background

MediBill Pro is a healthcare billing SaaS company headquartered in Nashville, TN, providing claims management, patient billing, and revenue cycle management software to hospitals, outpatient clinics, and specialty practices. With 200 employees and $22M ARR at the time of engagement, MediBill served 150 healthcare facilities across 18 states, primarily mid-size practices with 10-100 providers.

## Challenge

MediBill had recently transitioned from a traditional per-seat SaaS model to an outcome-based pricing model where customers paid based on successful claims processed and revenue collected. While the model aligned MediBill's incentives with customer outcomes, it created severe operational challenges:

- **Revenue recognition nightmare**: Outcome-based pricing meant revenue could only be recognized when claims were successfully adjudicated and payments received — a process spanning 30-120 days. The finance team was manually tracking $4.8M in deferred revenue across 150 facilities using spreadsheets.
- **Manual entitlement tracking**: Each facility's entitlements (number of provider licenses, claim volume tiers, add-on modules) were tracked in a combination of the CRM, billing spreadsheets, and email threads. 23% of facilities were using features they hadn't paid for, and 11% were being under-entitled relative to their contracts.
- **ASC 606 compliance risk**: The combination of outcome-based pricing, volume tiers, and bundled add-ons created complex performance obligations that the existing billing system couldn't model. External auditors flagged revenue recognition methodology as a "significant deficiency" in the prior annual audit.
- **Scaling bottleneck**: MediBill's growth team had a pipeline of 80+ qualified facilities, but onboarding was limited to 5-8 per quarter because each new facility required 2-3 weeks of manual billing configuration and entitlement setup.
- **HIPAA billing exposure**: Invoices and billing communications contained PHI (patient counts, claim volumes by diagnosis category), but the existing billing process lacked proper access controls and audit trails.

## Solution

MediBill deployed OmniGTM's outcome-based billing and entitlement engine to automate their revenue cycle:

1. **Outcome-based billing model** tracking claims lifecycle events (submission, adjudication, payment receipt) and automatically calculating billable amounts based on outcome tiers — replacing manual spreadsheet reconciliation.
2. **Automated entitlement management** syncing contract terms, feature access, and usage limits across the product platform — ensuring every facility had exactly the access their contract specified, no more and no less.
3. **ASC 606-compliant revenue recognition** with automated performance obligation identification, transaction price allocation, and revenue scheduling based on claim outcome timelines.
4. **HIPAA-compliant billing infrastructure** with role-based access controls, full audit trails on all billing data access, encrypted billing communications, and BAA-covered data handling for all PHI-adjacent billing metrics.
5. **Automated facility onboarding** with template-based billing configuration that compressed new facility setup from 2-3 weeks to 2 days, including entitlement provisioning, billing schedule configuration, and compliance validation.

Implementation took 10 weeks, including a 3-week parallel billing period where both systems ran simultaneously to validate accuracy.

## Results

After 12 months of running OmniGTM:

- **90% of revenue recognition automated** — from fully manual spreadsheet tracking to automated ASC 606-compliant revenue scheduling. Finance team reduced from 3 FTEs on rev rec to 0.5 FTE for exception handling.
- **Entitlement accuracy improved from 66% to 99.2%** — eliminating both over-entitlement (saving $380K in annual feature leakage) and under-entitlement (improving customer satisfaction scores by 18 points).
- **Audit finding remediated**: External auditors removed the "significant deficiency" designation in the first audit cycle post-deployment, citing automated controls and proper performance obligation tracking.
- **Facility count grew from 150 to 400** — onboarding capacity increased from 5-8 per quarter to 25-30 per quarter, enabling MediBill to work through their qualified pipeline in 10 months.
- **HIPAA compliance**: Zero billing-related HIPAA incidents in 12 months, with full audit trail coverage on all PHI-adjacent billing data.
- **Deferred revenue tracking**: $4.8M in deferred revenue now tracked automatically with real-time dashboards, reducing month-end close from 12 days to 4 days.
- **Revenue uplift of 28%**: Combination of eliminated feature leakage, accurate entitlement-based upselling, and faster facility onboarding drove ARR from $22M to $28.2M.

## Quote

> "When we moved to outcome-based pricing, we thought the hard part was designing the model. Turns out, the hard part was operationalizing it. We had $4.8 million in deferred revenue tracked in spreadsheets, auditors flagging our rev rec, and we couldn't onboard new facilities fast enough because billing setup took weeks. OmniGTM gave us an engine that actually understands outcome-based billing — not just subscriptions with extra steps. Going from 150 to 400 facilities in a year would have been impossible without it. And the HIPAA compliance piece isn't optional in healthcare — it's existential."
>
> — **Dr. Rana Patel, CEO, MediBill Pro**
