# Case Study: PayStream Global

## Company Background

PayStream Global is a payments platform headquartered in London, UK, providing payment processing, merchant services, and embedded finance APIs for e-commerce and SaaS companies. With 800 employees across offices in London, Singapore, São Paulo, and Toronto, PayStream serves 3,200+ merchants in 40 countries. At $112M ARR at the time of engagement, PayStream was in a phase of aggressive international expansion targeting 15 new markets within 18 months.

## Challenge

PayStream's international expansion was being throttled by pricing and billing complexity. Each new market required navigating local pricing norms, currency management, regulatory requirements, and competitive dynamics. Key problems included:

- **18-month projected timeline for 15 new markets**: Each market launch required 4-6 weeks of pricing research, 2-3 weeks of billing configuration, and 3-4 weeks of compliance review — totaling 10-13 weeks per market with sequential dependencies.
- **Currency management overhead**: Supporting 28 currencies with real-time exchange rate adjustments, local tax calculations, and settlement in local currency required 3 FTEs in finance operations.
- **Pricing inconsistency across regions**: Each regional GM set pricing independently, resulting in a 40% variance in effective take rates for equivalent merchant profiles across markets.
- **Compliance gaps**: Manual tracking of regional pricing regulations (interchange fee caps in the EU, surcharging rules in Australia, currency conversion disclosure requirements) led to 2 compliance findings in the prior 12 months.
- **Localization failures**: Flat-rate pricing imported from UK/US into markets like India and Southeast Asia resulted in 60% lower merchant activation rates compared to locally-optimized pricing.

## Solution

PayStream deployed OmniGTM's multi-currency pricing and regional packaging platform to standardize and accelerate international market launches:

1. **Regional pricing framework** with market-specific pricing templates incorporating local competitive benchmarks, regulatory constraints, and purchasing power adjustments — while maintaining global margin guardrails.
2. **Automated multi-currency billing** with real-time FX rate integration, local tax calculation (VAT, GST, withholding), and settlement in 40+ currencies — reducing finance operations from 3 FTEs to exception handling only.
3. **Compliance rule engine** encoding region-specific pricing regulations (EU Interchange Fee Regulation, Australian surcharging rules, Brazilian split-payment requirements) with automated validation on every pricing change.
4. **Localized packaging and pricing optimization** using market-specific merchant data to recommend pricing tiers, fee structures, and bundling strategies optimized for local merchant segments.
5. **Market launch playbook automation** compressing the pricing and billing workstream from 10-13 weeks to 3-4 weeks per market, with automated compliance checks and pricing simulation.

Implementation was phased over 12 weeks: core platform and 5 existing high-volume markets migrated in weeks 1-6, remaining 23 existing markets in weeks 7-10, and new market launch framework finalized in weeks 11-12.

## Results

After 12 months of running OmniGTM:

- **Launched in 12 new markets in 6 months** — versus the 18-month projection for 15 markets. On track to exceed the original 15-market target by month 9.
- **Market launch cycle compressed from 10-13 weeks to 3-4 weeks** — a 70% reduction driven by automated pricing templates, compliance validation, and billing configuration.
- **34% revenue uplift from localized pricing** — markets with locally-optimized pricing saw 34% higher revenue per merchant compared to flat-rate imported pricing, totaling $8.7M in incremental annual revenue.
- **Merchant activation rates improved by 52%** — in price-sensitive markets (India, Southeast Asia, Latin America), locally-tuned pricing and packaging drove activation from 23% to 35%.
- **Currency management FTEs reduced from 3 to 0.5** — automated FX, tax, and settlement processing eliminated 83% of manual finance operations work.
- **Zero compliance findings** in the 12 months since deployment, compared to 2 findings in the prior year.
- **Pricing variance across regions reduced from 40% to 8%** — global margin guardrails ensured consistent profitability while allowing local optimization.

## Quote

> "We were looking at 18 months to launch in 15 new markets, with each one requiring a small army of people to figure out pricing, currencies, taxes, and compliance. OmniGTM let us do 12 markets in 6 months with a smaller team. But the number that really matters is the 34% revenue uplift from localized pricing — we were leaving nearly $9 million on the table by importing our UK pricing into markets where it didn't fit. That's not a billing tool win, that's a strategy win."
>
> — **Sarah Okonkwo, CFO, PayStream Global**
