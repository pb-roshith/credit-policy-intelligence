# Policy classification taxonomy

**Status: PROPOSED — source-evidenced classifications for review.**

Generated: 2026-11-12T09:51:40.965464+00:00. Version: policy-classification-v1.

35 policies; 1609 stored source passages; 882 classified; 671 structural; 56 unclassified.

48 supported dictionary concepts; 0 unobserved; 699 observed tree nodes; 1779 proposed assignments.

[Open the review workbook](policy-taxonomy.xlsx) · [Full JSON](policy-taxonomy.json)

## Method and limits

- Curated controlled vocabulary; branches and assignments are materialized only from current source occurrences.
- Credit risk is the configured project domain. Policy area, product, segment and geography require literal passage evidence.
- Section headings select categories first; generic sections use literal passage matches. Topics are co-occurring terms, not extracted requirements.
- Training and evaluation sections are labelled TRAINING_MATERIAL and kept distinct from policy content.
- Multiple products/areas remain explicitly multiple; no cartesian combination or inherited document-wide scope is invented.
- Every stored current passage is classified, retained as structure or listed as unclassified. This is stored-text coverage, not OCR/page completeness.
- Assignments and vocabulary remain proposed. They do not approve policy scope, rules, ontology or executable field mappings.
- Unobserved vocabulary remains visible as NOT_OBSERVED and is excluded from the observed tree.
- Synthetic source labels are preserved, including imported documents labelled synthetic in their content.

## Observed classification tree

Each count is the number of distinct supporting passages. Unknown/multiple dimensions remain explicit.

```text
└── Credit risk [882]
    ├── Commercial [10]
    │   ├── Construction loan [1]
    │   │   └── Eligibility [1]
    │   │       ├── Bureau score [1]
    │   │       ├── Collateral valuation [1]
    │   │       ├── Credit rating [1]
    │   │       └── LTV [1]
    │   ├── Project finance [2]
    │   │   ├── Definitions [1]
    │   │   │   ├── Collateral haircut [1]
    │   │   │   ├── DSCR [1]
    │   │   │   ├── Income [1]
    │   │   │   ├── Interest and collateral coverage [1]
    │   │   │   └── LTV [1]
    │   │   └── Scope and applicability [2]
    │   │       ├── Collateral haircut [1]
    │   │       ├── DSCR [1]
    │   │       ├── Foreign currency risk [1]
    │   │       ├── Income [1]
    │   │       ├── Interest and collateral coverage [1]
    │   │       └── LTV [1]
    │   └── Unspecified product [7]
    │       ├── Approval authority [1]
    │       │   ├── Covenants [1]
    │       │   ├── DSCR [1]
    │       │   ├── Decision and escalation authority [1]
    │       │   ├── Interest and collateral coverage [1]
    │       │   └── Recovery and special assets [1]
    │       ├── Eligibility [2]
    │       │   ├── Collateral haircut [2]
    │       │   ├── Country risk [1]
    │       │   ├── Covenants [1]
    │       │   ├── Credit rating [1]
    │       │   └── Foreign currency risk [1]
    │       ├── Exceptions [2]
    │       │   ├── Decision and escalation authority [1]
    │       │   └── Tenor and duration [1]
    │       ├── Limits and thresholds [1]
    │       │   ├── Collateral haircut [1]
    │       │   ├── DSCR [1]
    │       │   ├── Decision and escalation authority [1]
    │       │   ├── Interest and collateral coverage [1]
    │       │   └── Portfolio liquidity [1]
    │       └── Scope and applicability [1]
    │           └── Country risk [1]
    ├── Commercial real estate [6]
    │   └── Unspecified product [6]
    │       ├── Approval authority [3]
    │       │   ├── Decision and escalation authority [1]
    │       │   └── Exposure and concentration [1]
    │       ├── Customer treatment and conduct [1]
    │       │   └── Decision and escalation authority [1]
    │       ├── Documentation [1]
    │       │   └── Decision and escalation authority [1]
    │       ├── Eligibility [2]
    │       │   ├── Decision and escalation authority [1]
    │       │   └── Exposure and concentration [1]
    │       ├── Exceptions [2]
    │       │   ├── Decision and escalation authority [1]
    │       │   └── Interest and collateral coverage [1]
    │       ├── Limits and thresholds [1]
    │       │   └── Exposure and concentration [1]
    │       ├── Monitoring [2]
    │       │   ├── Covenants [1]
    │       │   ├── Credit rating [1]
    │       │   ├── DSCR [1]
    │       │   ├── Exposure and concentration [2]
    │       │   ├── Recovery and special assets [1]
    │       │   └── Watchlist and early warning [1]
    │       ├── Purpose and objectives [1]
    │       │   └── Exposure and concentration [1]
    │       └── Reporting [2]
    │           └── Exposure and concentration [1]
    ├── Enterprise [9]
    │   └── Unspecified product [9]
    │       ├── Approval authority [4]
    │       │   ├── Covenants [1]
    │       │   ├── Credit rating [1]
    │       │   ├── Decision and escalation authority [3]
    │       │   ├── Exposure and concentration [4]
    │       │   └── Tenor and duration [1]
    │       ├── Exceptions [1]
    │       │   ├── Exposure and concentration [1]
    │       │   └── Tenor and duration [1]
    │       ├── Monitoring [3]
    │       │   ├── Decision and escalation authority [2]
    │       │   ├── Exposure and concentration [3]
    │       │   ├── Portfolio liquidity [1]
    │       │   └── Tenor and duration [2]
    │       ├── Purpose and objectives [1]
    │       │   ├── Decision and escalation authority [1]
    │       │   └── Spread and RAROC [1]
    │       ├── Reporting [1]
    │       │   └── Exposure and concentration [1]
    │       └── Scope and applicability [1]
    │           ├── Credit rating [1]
    │           ├── Exposure and concentration [1]
    │           └── Portfolio liquidity [1]
    ├── Multiple areas mentioned [34]
    │   ├── Construction loan [1]
    │   │   ├── Purpose and objectives [1]
    │   │   └── Scope and applicability [1]
    │   ├── Home loan [4]
    │   │   ├── Limits and thresholds [1]
    │   │   │   ├── Decision and escalation authority [1]
    │   │   │   └── Exposure and concentration [1]
    │   │   └── Scope and applicability [3]
    │   │       ├── Credit rating [1]
    │   │       ├── Exposure and concentration [1]
    │   │       ├── Portfolio liquidity [1]
    │   │       └── Tenor and duration [1]
    │   ├── Multiple products mentioned [5]
    │   │   ├── Eligibility [1]
    │   │   │   ├── Bureau score [1]
    │   │   │   ├── DSCR [1]
    │   │   │   ├── DTI [1]
    │   │   │   ├── Income [1]
    │   │   │   ├── Interest and collateral coverage [1]
    │   │   │   └── LTV [1]
    │   │   └── Scope and applicability [4]
    │   │       ├── DSCR [1]
    │   │       ├── Decision and escalation authority [1]
    │   │       ├── Income [1]
    │   │       ├── Portfolio liquidity [2]
    │   │       ├── Spread and RAROC [1]
    │   │       └── Tenor and duration [1]
    │   ├── Project finance [4]
    │   │   ├── Limits and thresholds [1]
    │   │   │   ├── Leverage [1]
    │   │   │   └── Spread and RAROC [1]
    │   │   └── Scope and applicability [3]
    │   │       ├── Credit rating [1]
    │   │       ├── Decision and escalation authority [1]
    │   │       ├── Income [1]
    │   │       ├── Required evidence [1]
    │   │       └── Spread and RAROC [2]
    │   └── Unspecified product [20]
    │       ├── Approval authority [1]
    │       │   ├── Bureau score [1]
    │       │   ├── Capital and RWA [1]
    │       │   ├── Exposure and concentration [1]
    │       │   ├── Interest and collateral coverage [1]
    │       │   └── Leverage [1]
    │       ├── Capital and provisioning [1]
    │       │   ├── Bureau score [1]
    │       │   ├── Capital and RWA [1]
    │       │   ├── Exposure and concentration [1]
    │       │   ├── Interest and collateral coverage [1]
    │       │   └── Leverage [1]
    │       ├── Collateral [1]
    │       │   ├── Credit rating [1]
    │       │   ├── DTI [1]
    │       │   ├── Income [1]
    │       │   ├── Interest and collateral coverage [1]
    │       │   ├── Leverage [1]
    │       │   └── Portfolio liquidity [1]
    │       ├── Data quality and evidence [1]
    │       │   ├── Credit rating [1]
    │       │   ├── Income [1]
    │       │   └── Spread and RAROC [1]
    │       ├── Documentation [1]
    │       │   ├── Bureau score [1]
    │       │   ├── Decision and escalation authority [1]
    │       │   ├── Income [1]
    │       │   └── Required evidence [1]
    │       ├── Eligibility [4]
    │       │   ├── Bureau score [1]
    │       │   ├── Credit rating [2]
    │       │   ├── DSCR [2]
    │       │   ├── Decision and escalation authority [2]
    │       │   ├── Exposure and concentration [2]
    │       │   ├── Income [2]
    │       │   ├── Interest and collateral coverage [1]
    │       │   ├── LTV [2]
    │       │   ├── Leverage [1]
    │       │   ├── Portfolio liquidity [1]
    │       │   ├── Recovery and special assets [1]
    │       │   ├── Required evidence [2]
    │       │   └── Spread and RAROC [1]
    │       ├── Exceptions [1]
    │       │   ├── Bureau score [1]
    │       │   ├── Capital and RWA [1]
    │       │   ├── Exposure and concentration [1]
    │       │   ├── Interest and collateral coverage [1]
    │       │   └── Leverage [1]
    │       ├── Limits and thresholds [6]
    │       │   ├── Bureau score [1]
    │       │   ├── Capital and RWA [2]
    │       │   ├── Collateral haircut [2]
    │       │   ├── Collateral valuation [1]
    │       │   ├── Credit rating [1]
    │       │   ├── Decision and escalation authority [1]
    │       │   ├── Exposure and concentration [5]
    │       │   ├── Interest and collateral coverage [1]
    │       │   ├── LTV [1]
    │       │   ├── Leverage [1]
    │       │   ├── Portfolio liquidity [2]
    │       │   ├── Tenor and duration [2]
    │       │   └── Watchlist and early warning [3]
    │       ├── Monitoring [2]
    │       │   ├── Collateral haircut [1]
    │       │   ├── Covenants [1]
    │       │   ├── Credit rating [1]
    │       │   ├── Decision and escalation authority [2]
    │       │   ├── Exposure and concentration [1]
    │       │   └── Watchlist and early warning [1]
    │       ├── Pricing and returns [1]
    │       │   ├── Credit rating [1]
    │       │   ├── Income [1]
    │       │   └── Spread and RAROC [1]
    │       ├── Purpose and objectives [3]
    │       │   ├── Capital and RWA [1]
    │       │   ├── Credit rating [1]
    │       │   ├── Exposure and concentration [2]
    │       │   └── Portfolio liquidity [1]
    │       ├── Scope and applicability [4]
    │       │   ├── Capital and RWA [1]
    │       │   ├── Credit rating [1]
    │       │   ├── Exposure and concentration [2]
    │       │   └── Portfolio liquidity [1]
    │       └── Servicing and collections [2]
    │           ├── Bureau score [1]
    │           ├── Capital and RWA [1]
    │           ├── Exposure and concentration [1]
    │           ├── Interest and collateral coverage [1]
    │           └── Leverage [1]
    ├── Retail [25]
    │   ├── Home loan [1]
    │   │   └── Eligibility [1]
    │   │       ├── Capital and RWA [1]
    │   │       └── Credit rating [1]
    │   ├── Multiple products mentioned [7]
    │   │   ├── Eligibility [1]
    │   │   │   ├── Collateral haircut [1]
    │   │   │   ├── Covenants [1]
    │   │   │   ├── DSCR [1]
    │   │   │   ├── Decision and escalation authority [1]
    │   │   │   ├── Interest and collateral coverage [1]
    │   │   │   └── Portfolio liquidity [1]
    │   │   ├── Limits and thresholds [2]
    │   │   │   ├── Bureau score [1]
    │   │   │   ├── Collateral valuation [1]
    │   │   │   ├── DSCR [1]
    │   │   │   ├── LTV [1]
    │   │   │   └── Leverage [1]
    │   │   ├── Purpose and objectives [1]
    │   │   │   └── LTV [1]
    │   │   └── Scope and applicability [3]
    │   │       ├── Collateral valuation [1]
    │   │       ├── LTV [1]
    │   │       ├── Leverage [1]
    │   │       ├── Portfolio liquidity [1]
    │   │       └── Tenor and duration [1]
    │   ├── Project finance [1]
    │   │   └── Scope and applicability [1]
    │   │       ├── Capital and RWA [1]
    │   │       ├── Credit rating [1]
    │   │       ├── Non-performing loans [1]
    │   │       └── Portfolio liquidity [1]
    │   ├── Revolving credit [1]
    │   │   ├── Approval authority [1]
    │   │   │   ├── Bureau score [1]
    │   │   │   ├── DSCR [1]
    │   │   │   ├── Decision and escalation authority [1]
    │   │   │   └── Income [1]
    │   │   ├── Documentation [1]
    │   │   │   ├── Bureau score [1]
    │   │   │   ├── DSCR [1]
    │   │   │   ├── Decision and escalation authority [1]
    │   │   │   └── Income [1]
    │   │   ├── Eligibility [1]
    │   │   │   ├── Bureau score [1]
    │   │   │   ├── DSCR [1]
    │   │   │   ├── Decision and escalation authority [1]
    │   │   │   └── Income [1]
    │   │   ├── Exceptions [1]
    │   │   │   ├── Bureau score [1]
    │   │   │   ├── DSCR [1]
    │   │   │   ├── Decision and escalation authority [1]
    │   │   │   └── Income [1]
    │   │   └── Limits and thresholds [1]
    │   │       ├── Bureau score [1]
    │   │       ├── DSCR [1]
    │   │       ├── Decision and escalation authority [1]
    │   │       └── Income [1]
    │   └── Unspecified product [15]
    │       ├── Approval authority [6]
    │       │   ├── Bureau score [1]
    │       │   ├── Capital and RWA [1]
    │       │   ├── Collateral valuation [1]
    │       │   ├── DSCR [2]
    │       │   ├── DTI [1]
    │       │   ├── Decision and escalation authority [2]
    │       │   └── LTV [3]
    │       ├── Collateral [2]
    │       │   ├── Bureau score [1]
    │       │   ├── Collateral valuation [1]
    │       │   ├── DTI [1]
    │       │   └── LTV [2]
    │       ├── Customer treatment and conduct [1]
    │       │   ├── Bureau score [1]
    │       │   ├── DTI [1]
    │       │   └── LTV [1]
    │       ├── Documentation [1]
    │       │   ├── Bureau score [1]
    │       │   ├── DTI [1]
    │       │   └── LTV [1]
    │       ├── Eligibility [4]
    │       │   ├── Bureau score [2]
    │       │   ├── Collateral valuation [1]
    │       │   ├── DSCR [2]
    │       │   ├── DTI [2]
    │       │   ├── Income [1]
    │       │   └── LTV [2]
    │       ├── Exceptions [5]
    │       │   ├── Bureau score [3]
    │       │   ├── Collateral valuation [1]
    │       │   ├── Covenants [1]
    │       │   ├── DSCR [2]
    │       │   ├── DTI [2]
    │       │   ├── Decision and escalation authority [1]
    │       │   ├── Income [1]
    │       │   ├── LTV [3]
    │       │   └── Portfolio liquidity [1]
    │       ├── Limits and thresholds [3]
    │       │   ├── Bureau score [1]
    │       │   ├── Collateral valuation [1]
    │       │   ├── Credit rating [1]
    │       │   ├── DTI [1]
    │       │   ├── Exposure and concentration [1]
    │       │   ├── LTV [2]
    │       │   ├── Non-performing loans [1]
    │       │   ├── Portfolio liquidity [1]
    │       │   └── Watchlist and early warning [1]
    │       ├── Monitoring [4]
    │       │   ├── Collateral valuation [1]
    │       │   ├── Covenants [1]
    │       │   ├── Credit rating [1]
    │       │   ├── DSCR [1]
    │       │   ├── Decision and escalation authority [1]
    │       │   ├── Interest and collateral coverage [1]
    │       │   └── LTV [2]
    │       ├── Purpose and objectives [1]
    │       │   ├── Capital and RWA [1]
    │       │   ├── DSCR [1]
    │       │   └── Interest and collateral coverage [1]
    │       ├── Reporting [3]
    │       │   ├── Collateral valuation [1]
    │       │   ├── DSCR [1]
    │       │   └── LTV [2]
    │       └── Scope and applicability [1]
    │           └── Decision and escalation authority [1]
    └── Unspecified area [798]
        ├── Construction loan [7]
        │   ├── Approval authority [3]
        │   │   ├── Credit rating [1]
        │   │   ├── Decision and escalation authority [1]
        │   │   ├── LTV [2]
        │   │   └── Watchlist and early warning [2]
        │   ├── Definitions [1]
        │   │   ├── Collateral valuation [1]
        │   │   └── LTV [1]
        │   ├── Documentation [1]
        │   │   └── Watchlist and early warning [1]
        │   ├── Eligibility [1]
        │   │   └── LTV [1]
        │   ├── Limits and thresholds [2]
        │   │   ├── DSCR [1]
        │   │   ├── Interest and collateral coverage [1]
        │   │   ├── LTV [1]
        │   │   └── Tenor and duration [1]
        │   ├── Monitoring [2]
        │   │   ├── Credit rating [1]
        │   │   ├── Decision and escalation authority [1]
        │   │   ├── LTV [1]
        │   │   └── Watchlist and early warning [1]
        │   ├── Reporting [1]
        │   │   └── Watchlist and early warning [1]
        │   └── Scope and applicability [1]
        │       ├── Collateral valuation [1]
        │       └── LTV [1]
        ├── Multiple products mentioned [9]
        │   ├── Approval authority [1]
        │   │   ├── DSCR [1]
        │   │   ├── Decision and escalation authority [1]
        │   │   └── Tenor and duration [1]
        │   ├── Definitions [1]
        │   │   ├── Covenants [1]
        │   │   ├── DSCR [1]
        │   │   ├── Income [1]
        │   │   ├── Interest and collateral coverage [1]
        │   │   └── Leverage [1]
        │   ├── Eligibility [3]
        │   │   ├── Bureau score [1]
        │   │   ├── Collateral valuation [1]
        │   │   ├── DSCR [1]
        │   │   ├── DTI [1]
        │   │   ├── Decision and escalation authority [1]
        │   │   ├── Income [1]
        │   │   ├── LTV [1]
        │   │   ├── Leverage [1]
        │   │   ├── Portfolio liquidity [1]
        │   │   └── Tenor and duration [2]
        │   ├── Exceptions [1]
        │   │   ├── DSCR [1]
        │   │   ├── Decision and escalation authority [1]
        │   │   └── Tenor and duration [1]
        │   ├── Limits and thresholds [2]
        │   │   ├── Credit rating [1]
        │   │   ├── DSCR [1]
        │   │   ├── Decision and escalation authority [1]
        │   │   ├── Exposure and concentration [1]
        │   │   └── Tenor and duration [2]
        │   ├── Purpose and objectives [5]
        │   │   ├── Capital and RWA [1]
        │   │   ├── DSCR [2]
        │   │   ├── Decision and escalation authority [3]
        │   │   ├── Exposure and concentration [1]
        │   │   ├── Interest and collateral coverage [1]
        │   │   ├── Leverage [1]
        │   │   ├── Portfolio liquidity [1]
        │   │   └── Tenor and duration [2]
        │   └── Scope and applicability [2]
        │       ├── Covenants [1]
        │       ├── DSCR [2]
        │       ├── Decision and escalation authority [1]
        │       ├── Income [1]
        │       ├── Interest and collateral coverage [2]
        │       └── Leverage [1]
        ├── Project finance [1]
        │   └── Exceptions [1]
        │       ├── Covenants [1]
        │       └── Decision and escalation authority [1]
        ├── Revolving credit [1]
        │   └── Eligibility [1]
        │       ├── Collateral haircut [1]
        │       ├── Credit rating [1]
        │       ├── Portfolio liquidity [1]
        │       └── Tenor and duration [1]
        ├── Term loan [2]
        │   ├── Approval authority [1]
        │   │   ├── Credit rating [1]
        │   │   ├── Decision and escalation authority [1]
        │   │   └── Tenor and duration [1]
        │   ├── Collateral [1]
        │   │   ├── Credit rating [1]
        │   │   ├── Decision and escalation authority [1]
        │   │   └── Tenor and duration [1]
        │   ├── Eligibility [1]
        │   │   ├── DSCR [1]
        │   │   ├── Interest and collateral coverage [1]
        │   │   ├── Spread and RAROC [1]
        │   │   └── Tenor and duration [1]
        │   ├── Exceptions [1]
        │   │   ├── Credit rating [1]
        │   │   ├── Decision and escalation authority [1]
        │   │   └── Tenor and duration [1]
        │   └── Purpose and objectives [1]
        │       ├── Credit rating [1]
        │       ├── Decision and escalation authority [1]
        │       └── Tenor and duration [1]
        └── Unspecified product [778]
            ├── AI governance [74]
            │   ├── Collection treatment [1]
            │   └── Non-performing loans [1]
            ├── Approval authority [210]
            │   ├── Capital and RWA [15]
            │   ├── Collateral haircut [3]
            │   ├── Collateral valuation [2]
            │   ├── Collection treatment [3]
            │   ├── Country risk [4]
            │   ├── Covenants [8]
            │   ├── Credit rating [8]
            │   ├── Decision and escalation authority [46]
            │   ├── Exposure and concentration [15]
            │   ├── Foreign currency risk [3]
            │   ├── Interest and collateral coverage [3]
            │   ├── LTV [1]
            │   ├── Leverage [6]
            │   ├── Portfolio liquidity [6]
            │   ├── Recovery and special assets [3]
            │   ├── Required evidence [1]
            │   ├── Spread and RAROC [9]
            │   ├── Tenor and duration [6]
            │   └── Write-off [1]
            ├── Capital and provisioning [9]
            │   ├── Capital and RWA [4]
            │   ├── Collection treatment [1]
            │   ├── Country risk [1]
            │   ├── Covenants [1]
            │   ├── Decision and escalation authority [3]
            │   ├── Leverage [2]
            │   ├── Portfolio liquidity [1]
            │   └── Spread and RAROC [2]
            ├── Collateral [13]
            │   ├── Collateral haircut [3]
            │   ├── Covenants [1]
            │   ├── Decision and escalation authority [1]
            │   ├── Interest and collateral coverage [1]
            │   ├── LTV [1]
            │   ├── Recovery and special assets [5]
            │   └── Write-off [1]
            ├── Customer treatment and conduct [20]
            │   ├── Capital and RWA [2]
            │   ├── Covenants [1]
            │   ├── Days past due [1]
            │   ├── Decision and escalation authority [1]
            │   ├── Hardship and forbearance [1]
            │   ├── Leverage [1]
            │   ├── Recovery and special assets [2]
            │   └── Tenor and duration [1]
            ├── Data quality and evidence [1]
            │   ├── Decision and escalation authority [1]
            │   └── Spread and RAROC [1]
            ├── Definitions [52]
            │   ├── Collection treatment [5]
            │   ├── Days past due [1]
            │   ├── Debt sale [1]
            │   ├── Decision and escalation authority [1]
            │   ├── Hardship and forbearance [2]
            │   ├── Non-performing loans [2]
            │   ├── Recovery and special assets [10]
            │   ├── Restructuring and modification [4]
            │   ├── Watchlist and early warning [3]
            │   └── Write-off [6]
            ├── Documentation [6]
            │   ├── Collateral haircut [2]
            │   ├── Covenants [2]
            │   ├── Credit rating [2]
            │   ├── DSCR [1]
            │   ├── Decision and escalation authority [4]
            │   ├── Interest and collateral coverage [1]
            │   ├── LTV [1]
            │   ├── Portfolio liquidity [1]
            │   ├── Required evidence [1]
            │   └── Watchlist and early warning [1]
            ├── Eligibility [18]
            │   ├── Capital and RWA [1]
            │   ├── Collateral haircut [4]
            │   ├── Collateral valuation [1]
            │   ├── Country risk [2]
            │   ├── Covenants [1]
            │   ├── Credit rating [2]
            │   ├── DSCR [1]
            │   ├── Decision and escalation authority [9]
            │   ├── Exposure and concentration [2]
            │   ├── Foreign currency risk [1]
            │   ├── Interest and collateral coverage [3]
            │   ├── LTV [1]
            │   ├── Leverage [3]
            │   ├── Portfolio liquidity [3]
            │   ├── Required evidence [1]
            │   └── Tenor and duration [2]
            ├── Exceptions [103]
            │   ├── Capital and RWA [15]
            │   ├── Collateral haircut [3]
            │   ├── Country risk [2]
            │   ├── Covenants [5]
            │   ├── DSCR [2]
            │   ├── Decision and escalation authority [16]
            │   ├── Exposure and concentration [13]
            │   ├── Foreign currency risk [2]
            │   ├── Interest and collateral coverage [2]
            │   ├── LTV [2]
            │   ├── Leverage [3]
            │   ├── Portfolio liquidity [4]
            │   ├── Required evidence [1]
            │   ├── Restructuring and modification [3]
            │   ├── Spread and RAROC [5]
            │   └── Tenor and duration [3]
            ├── Limits and thresholds [38]
            │   ├── Capital and RWA [5]
            │   ├── Collateral haircut [2]
            │   ├── Collection treatment [1]
            │   ├── Country risk [5]
            │   ├── Covenants [5]
            │   ├── Credit rating [4]
            │   ├── DSCR [2]
            │   ├── Decision and escalation authority [12]
            │   ├── Exposure and concentration [6]
            │   ├── Foreign currency risk [1]
            │   ├── Income [1]
            │   ├── Interest and collateral coverage [4]
            │   ├── LTV [1]
            │   ├── Leverage [7]
            │   ├── Portfolio liquidity [6]
            │   ├── Spread and RAROC [3]
            │   ├── Tenor and duration [2]
            │   └── Watchlist and early warning [1]
            ├── Monitoring [105]
            │   ├── Capital and RWA [14]
            │   ├── Collateral haircut [2]
            │   ├── Collateral valuation [1]
            │   ├── Country risk [2]
            │   ├── Covenants [5]
            │   ├── Credit rating [3]
            │   ├── DSCR [2]
            │   ├── Decision and escalation authority [12]
            │   ├── Exposure and concentration [13]
            │   ├── Foreign currency risk [1]
            │   ├── Interest and collateral coverage [3]
            │   ├── LTV [1]
            │   ├── Leverage [5]
            │   ├── Non-performing loans [1]
            │   ├── Portfolio liquidity [1]
            │   ├── Spread and RAROC [3]
            │   ├── Tenor and duration [4]
            │   └── Watchlist and early warning [8]
            ├── Pricing and returns [3]
            │   ├── Decision and escalation authority [2]
            │   └── Spread and RAROC [3]
            ├── Purpose and objectives [77]
            │   ├── Capital and RWA [6]
            │   ├── Collateral haircut [2]
            │   ├── Collection treatment [2]
            │   ├── Country risk [3]
            │   ├── Covenants [1]
            │   ├── Credit rating [3]
            │   ├── DSCR [1]
            │   ├── Days past due [1]
            │   ├── Decision and escalation authority [24]
            │   ├── Exposure and concentration [3]
            │   ├── Foreign currency risk [2]
            │   ├── Hardship and forbearance [1]
            │   ├── Income [2]
            │   ├── Interest and collateral coverage [3]
            │   ├── Leverage [2]
            │   ├── Non-performing loans [1]
            │   ├── Portfolio liquidity [4]
            │   ├── Recovery and special assets [3]
            │   ├── Required evidence [1]
            │   ├── Spread and RAROC [2]
            │   ├── Tenor and duration [2]
            │   ├── Watchlist and early warning [2]
            │   └── Write-off [1]
            ├── Remediation and recovery [52]
            │   ├── Days past due [1]
            │   ├── Hardship and forbearance [6]
            │   ├── Non-performing loans [5]
            │   ├── Recovery and special assets [24]
            │   ├── Restructuring and modification [6]
            │   ├── Watchlist and early warning [1]
            │   └── Write-off [9]
            ├── Reporting [32]
            │   ├── Capital and RWA [3]
            │   ├── Collateral haircut [2]
            │   ├── Country risk [2]
            │   ├── Covenants [3]
            │   ├── Credit rating [9]
            │   ├── DSCR [2]
            │   ├── Decision and escalation authority [10]
            │   ├── Exposure and concentration [4]
            │   ├── Foreign currency risk [1]
            │   ├── Interest and collateral coverage [1]
            │   ├── LTV [2]
            │   ├── Leverage [2]
            │   ├── Non-performing loans [2]
            │   ├── Portfolio liquidity [3]
            │   ├── Required evidence [1]
            │   ├── Spread and RAROC [2]
            │   ├── Tenor and duration [3]
            │   └── Watchlist and early warning [3]
            ├── Scope and applicability [25]
            │   ├── Capital and RWA [2]
            │   ├── Collateral haircut [1]
            │   ├── Covenants [2]
            │   ├── Credit rating [2]
            │   ├── DSCR [1]
            │   ├── Decision and escalation authority [3]
            │   ├── Interest and collateral coverage [2]
            │   ├── Leverage [2]
            │   ├── Non-performing loans [2]
            │   ├── Recovery and special assets [2]
            │   ├── Restructuring and modification [1]
            │   ├── Tenor and duration [1]
            │   ├── Watchlist and early warning [2]
            │   └── Write-off [1]
            ├── Servicing and collections [20]
            │   ├── Collection treatment [10]
            │   ├── Covenants [2]
            │   ├── Days past due [1]
            │   ├── Leverage [1]
            │   ├── Non-performing loans [3]
            │   ├── Portfolio liquidity [1]
            │   └── Watchlist and early warning [1]
            └── Training and evaluation [170]
                ├── Collection treatment [4]
                ├── Covenants [1]
                ├── Debt sale [1]
                ├── Decision and escalation authority [3]
                ├── Hardship and forbearance [1]
                ├── Income [1]
                ├── Non-performing loans [3]
                ├── Portfolio liquidity [1]
                ├── Recovery and special assets [10]
                ├── Restructuring and modification [4]
                ├── Watchlist and early warning [1]
                └── Write-off [5]
```

## Controlled dictionary

| Concept | Kind | Supporting passages | Status |
|---|---|---:|---|
| Eligibility | CATEGORY | 41 | SOURCE_SUPPORTED |
| Limits and thresholds | CATEGORY | 58 | SOURCE_SUPPORTED |
| Collateral | CATEGORY | 17 | SOURCE_SUPPORTED |
| Documentation | CATEGORY | 11 | SOURCE_SUPPORTED |
| Exceptions | CATEGORY | 118 | SOURCE_SUPPORTED |
| Approval authority | CATEGORY | 231 | SOURCE_SUPPORTED |
| Monitoring | CATEGORY | 118 | SOURCE_SUPPORTED |
| Reporting | CATEGORY | 39 | SOURCE_SUPPORTED |
| Servicing and collections | CATEGORY | 22 | SOURCE_SUPPORTED |
| Remediation and recovery | CATEGORY | 52 | SOURCE_SUPPORTED |
| Pricing and returns | CATEGORY | 4 | SOURCE_SUPPORTED |
| Capital and provisioning | CATEGORY | 10 | SOURCE_SUPPORTED |
| Scope and applicability | CATEGORY | 52 | SOURCE_SUPPORTED |
| Definitions | CATEGORY | 55 | SOURCE_SUPPORTED |
| Data quality and evidence | CATEGORY | 2 | SOURCE_SUPPORTED |
| Customer treatment and conduct | CATEGORY | 22 | SOURCE_SUPPORTED |
| AI governance | CATEGORY | 74 | SOURCE_SUPPORTED |
| Purpose and objectives | CATEGORY | 91 | SOURCE_SUPPORTED |
| Training and evaluation | CATEGORY | 170 | SOURCE_SUPPORTED |
| LTV | TOPIC | 22 | SOURCE_SUPPORTED |
| Income | TOPIC | 17 | SOURCE_SUPPORTED |
| Bureau score | TOPIC | 11 | SOURCE_SUPPORTED |
| DTI | TOPIC | 6 | SOURCE_SUPPORTED |
| DSCR | TOPIC | 31 | SOURCE_SUPPORTED |
| Leverage | TOPIC | 31 | SOURCE_SUPPORTED |
| Tenor and duration | TOPIC | 32 | SOURCE_SUPPORTED |
| Credit rating | TOPIC | 50 | SOURCE_SUPPORTED |
| Collateral valuation | TOPIC | 11 | SOURCE_SUPPORTED |
| Collateral haircut | TOPIC | 21 | SOURCE_SUPPORTED |
| Interest and collateral coverage | TOPIC | 31 | SOURCE_SUPPORTED |
| Exposure and concentration | TOPIC | 69 | SOURCE_SUPPORTED |
| Country risk | TOPIC | 18 | SOURCE_SUPPORTED |
| Foreign currency risk | TOPIC | 11 | SOURCE_SUPPORTED |
| Portfolio liquidity | TOPIC | 42 | SOURCE_SUPPORTED |
| Covenants | TOPIC | 35 | SOURCE_SUPPORTED |
| Spread and RAROC | TOPIC | 25 | SOURCE_SUPPORTED |
| Capital and RWA | TOPIC | 48 | SOURCE_SUPPORTED |
| Days past due | TOPIC | 5 | SOURCE_SUPPORTED |
| Collection treatment | TOPIC | 23 | SOURCE_SUPPORTED |
| Hardship and forbearance | TOPIC | 10 | SOURCE_SUPPORTED |
| Restructuring and modification | TOPIC | 18 | SOURCE_SUPPORTED |
| Non-performing loans | TOPIC | 19 | SOURCE_SUPPORTED |
| Watchlist and early warning | TOPIC | 29 | SOURCE_SUPPORTED |
| Recovery and special assets | TOPIC | 55 | SOURCE_SUPPORTED |
| Write-off | TOPIC | 22 | SOURCE_SUPPORTED |
| Debt sale | TOPIC | 2 | SOURCE_SUPPORTED |
| Decision and escalation authority | TOPIC | 125 | SOURCE_SUPPORTED |
| Required evidence | TOPIC | 7 | SOURCE_SUPPORTED |

## Explicitly observed dimensions

- customer_segment: Corporate (7), SME (2)
- policy_area: Commercial (41), Commercial real estate (28), Enterprise (11), Retail (49), SME (4)
- product: Auto loan (6), Construction loan (9), Credit card (5), Home equity line of credit (3), Home loan (12), Project finance (12), Revolving credit (12), Secured personal loan (4), Term loan (16), Working capital (1)

## Source examples

**Credit risk → Retail → Unspecified product → Scope and applicability → Decision and escalation authority**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-4 · page 2 · synthetic: True

> 2. 2. Scope
> The scope of this clause, 4.1 Underwriting Standards, encompasses all wholesale credit exposures originated, renewed, or
> amended by the bank. Wholesale credit exposures are defined as those extended to corporate entities, financial institutions,
> sovereigns, and other non-retail counterparties with an aggregate exposure of USD 1,000,000 or more. This threshold ensures
> that the underwriting standards are applied consistently across the bank’s wholesale portfolio.
> The clause applies to all business lines and geographic regions where the bank operates, unless explicitly exempted by the
> Global Credit Policy Committee. Exemptions must be documented and justified based on local regulatory requirements or
> unique market conditions. All personnel involved in the underwriting process, including relationship managers, credit analysts,
> and approval authorities, are required to comply with… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Approval authority → Credit rating**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-6 · page 3 · synthetic: True

> 3. 3. Governance and Roles
> The governance framework for underwriting standards is designed to ensure clear accountability, segregation of duties, and
> independent oversight. The Global Credit Policy Committee (GCPC) is the ultimate authority responsible for the approval and
> periodic review of this clause. The GCPC delegates day-to-day oversight to the Wholesale Credit Risk Division, which is
> responsible for implementing and enforcing the underwriting standards.
> The Wholesale Credit Risk Division is led by the Chief Credit Officer (CCO) for Wholesale Banking, who reports directly to the
> GCPC. The CCO is responsible for ensuring that all underwriting activities adhere to the standards outlined in this clause and
> that any exceptions are properly escalated and documented. The division includes regional credit officers, industry specialists,
> and portfolio managers who provide subject-matter ex… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Eligibility → Leverage**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-8 · page 4 · synthetic: True

> 4. 4. Underwriting Criteria
> The underwriting criteria outlined in this section define the qualitative and quantitative factors that must be evaluated to assess
> the creditworthiness of wholesale clients. The criteria are designed to provide a comprehensive view of the borrower’s ability
> and willingness to repay its obligations. The evaluation must include an assessment of the borrower’s financial strength,
> industry risk, management quality, competitive position, and collateral adequacy.
> Financial strength is evaluated through a detailed analysis of the borrower’s historical and projected financial statements. Key
> metrics include leverage ratios (e.g., Debt/EBITDA, Total Debt/Total Capital), coverage ratios (e.g., Interest Coverage, Fixed
> Charge Coverage), liquidity ratios (e.g., Current Ratio, Quick Ratio), and profitability trends. For Tier 1 and Tier 2 clients, a
> minimum Interest Covera… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Eligibility → Collateral valuation**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-8 · page 4 · synthetic: True

> 4. 4. Underwriting Criteria
> The underwriting criteria outlined in this section define the qualitative and quantitative factors that must be evaluated to assess
> the creditworthiness of wholesale clients. The criteria are designed to provide a comprehensive view of the borrower’s ability
> and willingness to repay its obligations. The evaluation must include an assessment of the borrower’s financial strength,
> industry risk, management quality, competitive position, and collateral adequacy.
> Financial strength is evaluated through a detailed analysis of the borrower’s historical and projected financial statements. Key
> metrics include leverage ratios (e.g., Debt/EBITDA, Total Debt/Total Capital), coverage ratios (e.g., Interest Coverage, Fixed
> Charge Coverage), liquidity ratios (e.g., Current Ratio, Quick Ratio), and profitability trends. For Tier 1 and Tier 2 clients, a
> minimum Interest Covera… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Eligibility → Collateral haircut**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-8 · page 4 · synthetic: True

> 4. 4. Underwriting Criteria
> The underwriting criteria outlined in this section define the qualitative and quantitative factors that must be evaluated to assess
> the creditworthiness of wholesale clients. The criteria are designed to provide a comprehensive view of the borrower’s ability
> and willingness to repay its obligations. The evaluation must include an assessment of the borrower’s financial strength,
> industry risk, management quality, competitive position, and collateral adequacy.
> Financial strength is evaluated through a detailed analysis of the borrower’s historical and projected financial statements. Key
> metrics include leverage ratios (e.g., Debt/EBITDA, Total Debt/Total Capital), coverage ratios (e.g., Interest Coverage, Fixed
> Charge Coverage), liquidity ratios (e.g., Current Ratio, Quick Ratio), and profitability trends. For Tier 1 and Tier 2 clients, a
> minimum Interest Covera… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Eligibility → Interest and collateral coverage**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-8 · page 4 · synthetic: True

> 4. 4. Underwriting Criteria
> The underwriting criteria outlined in this section define the qualitative and quantitative factors that must be evaluated to assess
> the creditworthiness of wholesale clients. The criteria are designed to provide a comprehensive view of the borrower’s ability
> and willingness to repay its obligations. The evaluation must include an assessment of the borrower’s financial strength,
> industry risk, management quality, competitive position, and collateral adequacy.
> Financial strength is evaluated through a detailed analysis of the borrower’s historical and projected financial statements. Key
> metrics include leverage ratios (e.g., Debt/EBITDA, Total Debt/Total Capital), coverage ratios (e.g., Interest Coverage, Fixed
> Charge Coverage), liquidity ratios (e.g., Current Ratio, Quick Ratio), and profitability trends. For Tier 1 and Tier 2 clients, a
> minimum Interest Covera… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Eligibility → Portfolio liquidity**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-8 · page 4 · synthetic: True

> 4. 4. Underwriting Criteria
> The underwriting criteria outlined in this section define the qualitative and quantitative factors that must be evaluated to assess
> the creditworthiness of wholesale clients. The criteria are designed to provide a comprehensive view of the borrower’s ability
> and willingness to repay its obligations. The evaluation must include an assessment of the borrower’s financial strength,
> industry risk, management quality, competitive position, and collateral adequacy.
> Financial strength is evaluated through a detailed analysis of the borrower’s historical and projected financial statements. Key
> metrics include leverage ratios (e.g., Debt/EBITDA, Total Debt/Total Capital), coverage ratios (e.g., Interest Coverage, Fixed
> Charge Coverage), liquidity ratios (e.g., Current Ratio, Quick Ratio), and profitability trends. For Tier 1 and Tier 2 clients, a
> minimum Interest Covera… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Limits and thresholds → Exposure and concentration**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-10 · page 5 · synthetic: True

> 5. 5. Quantitative Limits
> Quantitative limits are established to ensure that credit exposures remain within the bank’s risk appetite and regulatory
> constraints. These limits are applied at various levels, including individual borrowers, industry sectors, geographic regions, and
> product types. The limits are designed to prevent excessive concentration risk and to ensure diversification across the
> wholesale portfolio.
> The bank’s aggregate wholesale credit exposure to a single borrower or borrower group must not exceed 15% of the bank’s
> Tier 1 capital, as defined by regulatory guidelines. For Tier 1 clients, the maximum exposure is capped at USD 500 million,
> unless approved by the GCPC. For Tier 2 clients, the cap is USD 200 million, and for Tier 3 clients, it is USD 50 million.
> Exposures exceeding these thresholds require a detailed concentration risk analysis and approval from the CCO for… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Limits and thresholds → Country risk**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-10 · page 5 · synthetic: True

> 5. 5. Quantitative Limits
> Quantitative limits are established to ensure that credit exposures remain within the bank’s risk appetite and regulatory
> constraints. These limits are applied at various levels, including individual borrowers, industry sectors, geographic regions, and
> product types. The limits are designed to prevent excessive concentration risk and to ensure diversification across the
> wholesale portfolio.
> The bank’s aggregate wholesale credit exposure to a single borrower or borrower group must not exceed 15% of the bank’s
> Tier 1 capital, as defined by regulatory guidelines. For Tier 1 clients, the maximum exposure is capped at USD 500 million,
> unless approved by the GCPC. For Tier 2 clients, the cap is USD 200 million, and for Tier 3 clients, it is USD 50 million.
> Exposures exceeding these thresholds require a detailed concentration risk analysis and approval from the CCO for… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Approval authority → Covenants**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-12 · page 6 · synthetic: True

> 6. 6. Approval Authorities and Escalation Paths
> Approval authorities are delegated based on the risk profile, size, and complexity of the credit exposure. The approval matrix
> ensures that higher-risk or larger exposures receive appropriate levels of scrutiny and oversight. The matrix is structured to
> align with the bank’s risk appetite and regulatory expectations, and it is reviewed annually by the GCPC.
> For Tier 3 clients with exposures up to USD 10 million, approval authority is delegated to the regional credit officer. Exposures
> between USD 10 million and USD 50 million require approval from the regional credit committee, which includes
> representatives from the Wholesale Credit Risk Division and the business line. For Tier 2 clients, exposures up to USD 50
> million require regional credit committee approval, while exposures between USD 50 million and USD 200 million require
> approval fr… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Monitoring → Watchlist and early warning**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-14 · page 7 · synthetic: True

> 7. 7. Monitoring and Ongoing Review
> Ongoing monitoring is a critical component of the underwriting process, ensuring that the bank’s credit exposures remain
> consistent with the initial underwriting assessment. The Wholesale Credit Risk Division is responsible for establishing and
> maintaining a robust monitoring framework that includes financial covenant tracking, credit rating reviews, and early warning
> indicators.
> Financial covenants are tailored to the borrower’s risk profile and are designed to provide early warning of potential credit
> deterioration. Common covenants include minimum Interest Coverage Ratios, maximum Leverage Ratios, and minimum net
> worth requirements. Covenant compliance is monitored quarterly, and breaches must be investigated and reported to the
> appropriate credit committee within 10 business days. Persistent or material covenant breaches may trigger a review of the… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Documentation → Required evidence**

4.1 Underwriting Standards · version 4.2 · CPI-CLAUSE-18 · page 9 · synthetic: True

> 9. 9. Reporting and Documentation
> Accurate and comprehensive reporting and documentation are essential to the integrity of the underwriting process. The bank
> maintains a centralized credit file for each wholesale borrower, which serves as the official record of all underwriting activities,
> approvals, monitoring, and exceptions. The credit file must be complete, up-to-date, and accessible to all relevant stakeholders,
> including relationship managers, credit analysts, and auditors.
> The credit file must include all documents and analyses used to support the underwriting decision, such as financial statements,
> industry reports, management assessments, and collateral valuations. For new credit requests, the file must also include the
> credit application, approval memorandum, and any exception or waiver requests. For existing exposures, the file must be
> updated with the results of ongoing monit… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Limits and thresholds → DSCR**

4.2 Leverage Limits · version 4.2 · CPI-CLAUSE-30 · page 5 · synthetic: True

> 5. 5. Quantitative Limits
> The quantitative leverage limits under this clause are structured to provide a clear and actionable framework for credit
> decision-making. The bank employs a tiered approach to leverage limits, with thresholds varying by credit rating, industry, and
> transaction type. For investment-grade corporate borrowers, the maximum permitted Total Debt to EBITDA ratio is 4.5x, while
> for non-investment-grade borrowers, the limit is capped at 3.5x. These limits are subject to further adjustments based on the
> borrower’s cash flow stability, asset quality, and access to liquidity.
> For leveraged finance transactions, including LBOs and acquisition financing, the bank imposes stricter limits. The maximum
> Total Debt to EBITDA ratio for such transactions is 6.0x for senior debt and 7.0x for total debt, including mezzanine financing.
> These limits are designed to reflect the higher ri… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Exceptions → Restructuring and modification**

4.2 Leverage Limits · version 4.2 · CPI-CLAUSE-36 · page 8 · synthetic: True

> 8. 8. Exception Management
> Exception management under this clause is designed to ensure that any deviations from the established leverage limits are
> identified, documented, and resolved in a timely and controlled manner. The bank’s exception management framework is
> governed by the principle that exceptions should be rare, justified, and subject to rigorous oversight.
> All leverage limit exceptions must be logged in the bank’s centralized exception tracking system, which captures details such as
> the borrower’s name, the nature and magnitude of the breach, the approval authority, and the rationale for the exception. The
> system also tracks the status of corrective action plans and the timeline for resolution. Exceptions are categorized by severity,
> with Tier 1, Tier 2, and Tier 3 classifications aligning with the approval authority hierarchy.
> This clause is synthetic demonstration data, and … [full passage in workbook/JSON]

**Credit risk → Unspecified area → Multiple products mentioned → Purpose and objectives → Tenor and duration**

4.3 Tenor Limits · version 4.2 · CPI-CLAUSE-53 · page 1 · synthetic: True

> 1. 1. Purpose
> The purpose of Clause 4.3 Tenor Limits under the Parent Policy CP-Wholesale-v4.2 is to establish a structured framework for
> managing the tenor of credit exposures extended to wholesale clients. This clause ensures that the bank’s credit risk appetite is
> aligned with the tenor of obligations assumed, thereby mitigating the potential for liquidity mismatches, concentration risk, and
> long-term exposure to adverse market conditions. By defining clear tenor limits, the bank aims to balance its commitment to
> supporting client needs with prudent risk management practices.
> Tenor limits are critical in ensuring that the bank’s assets and liabilities are appropriately matched, reducing the risk of liquidity
> shortfalls that could arise from an overconcentration of long-term lending without corresponding long-term funding. This clause
> provides the necessary guidelines to underwriters, … [full passage in workbook/JSON]

**Credit risk → Unspecified area → Multiple products mentioned → Purpose and objectives → Capital and RWA**

4.3 Tenor Limits · version 4.2 · CPI-CLAUSE-53 · page 1 · synthetic: True

> 1. 1. Purpose
> The purpose of Clause 4.3 Tenor Limits under the Parent Policy CP-Wholesale-v4.2 is to establish a structured framework for
> managing the tenor of credit exposures extended to wholesale clients. This clause ensures that the bank’s credit risk appetite is
> aligned with the tenor of obligations assumed, thereby mitigating the potential for liquidity mismatches, concentration risk, and
> long-term exposure to adverse market conditions. By defining clear tenor limits, the bank aims to balance its commitment to
> supporting client needs with prudent risk management practices.
> Tenor limits are critical in ensuring that the bank’s assets and liabilities are appropriately matched, reducing the risk of liquidity
> shortfalls that could arise from an overconcentration of long-term lending without corresponding long-term funding. This clause
> provides the necessary guidelines to underwriters, … [full passage in workbook/JSON]

**Credit risk → Unspecified area → Multiple products mentioned → Scope and applicability → Income**

4.4 Covenant Package · version 4.2 · CPI-CLAUSE-75 · page 2 · synthetic: True

> 2. 2. Scope and Definitions
> This Policy applies to all wholesale credit exposures, including but not limited to bilateral loans, syndicated facilities, revolving
> credit agreements, term loans, and other structured credit products. It covers all jurisdictions in which the Bank operates, unless
> superseded by local regulatory requirements or specific legal constraints.
> For the purposes of this Policy, the term 'covenant' refers to any condition or requirement stipulated in a credit agreement that
> the borrower must fulfill. Covenants are classified into two primary categories: (1) Financial Covenants, which are quantitative
> measures of the borrower’s financial health, and (2) Non-Financial Covenants, which are qualitative or operational conditions
> that the borrower must meet.
> Financial Covenants include, but are not limited to, the following: (a) Maximum Leverage Ratio (Total Debt/EBITDA), (… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Limits and thresholds → Collection treatment**

4.4 Covenant Package · version 4.2 · CPI-CLAUSE-79 · page 4 · synthetic: True

> 4. 4. Covenant Structuring Principles
> The structuring of the Covenant Package must be guided by the principle of risk proportionality, ensuring that the stringency of
> the covenants is commensurate with the risk profile of the borrower and the nature of the exposure. Higher-risk borrowers or
> transactions must be subject to more stringent covenants, including lower leverage thresholds and higher coverage ratios.
> Financial covenants must be based on the borrower’s historical and projected financial performance, as well as industry
> benchmarks. The Bank must use a minimum of three years of historical financial data to establish baseline covenant
> thresholds. For borrowers with volatile financial performance, the Bank may require additional buffers or more frequent testing
> of covenants.
> Non-financial covenants must address key operational and legal risks identified during the due diligence proc… [full passage in workbook/JSON]

**Credit risk → Retail → Unspecified product → Eligibility → Bureau score**

3.1 DSCR Minimums · version 3.1 · CPI-CLAUSE-100 · page 4 · synthetic: True

> 4. 4. Underwriting Criteria
> The underwriting criteria for DSCR minimums are designed to ensure that borrowers demonstrate sufficient cash flow to service
> their debt obligations. For retail credit products, the DSCR is calculated as the ratio of the borrower's net operating income to
> their total debt service, including principal, interest, and any other mandatory payments. The minimum DSCR threshold for
> standard retail loans is set at 1.25x, meaning that the borrower's net operating income must be at least 1.25 times their total
> debt service.
> For borrowers with a credit score below 650, the minimum DSCR threshold is increased to 1.50x to account for the higher risk
> profile. Conversely, borrowers with a credit score above 750 and a demonstrated history of stable income may qualify for a
> reduced DSCR minimum of 1.15x, subject to additional controls and approvals. These thresholds are synthe… [full passage in workbook/JSON]

**Credit risk → Retail → Unspecified product → Eligibility → DTI**

3.1 DSCR Minimums · version 3.1 · CPI-CLAUSE-100 · page 4 · synthetic: True

> 4. 4. Underwriting Criteria
> The underwriting criteria for DSCR minimums are designed to ensure that borrowers demonstrate sufficient cash flow to service
> their debt obligations. For retail credit products, the DSCR is calculated as the ratio of the borrower's net operating income to
> their total debt service, including principal, interest, and any other mandatory payments. The minimum DSCR threshold for
> standard retail loans is set at 1.25x, meaning that the borrower's net operating income must be at least 1.25 times their total
> debt service.
> For borrowers with a credit score below 650, the minimum DSCR threshold is increased to 1.50x to account for the higher risk
> profile. Conversely, borrowers with a credit score above 750 and a demonstrated history of stable income may qualify for a
> reduced DSCR minimum of 1.15x, subject to additional controls and approvals. These thresholds are synthe… [full passage in workbook/JSON]

**Credit risk → Retail → Multiple products mentioned → Purpose and objectives → LTV**

3.2 LTV Ceilings · version 3.1 · CPI-CLAUSE-119 · page 1 · synthetic: True

> 1. 1. Purpose
> The purpose of this clause, 3.2 LTV Ceilings, under the parent policy CP-Retail-v3.1, is to establish clear, consistent, and
> risk-based Loan-to-Value (LTV) ceilings for all retail lending products offered by the bank. This clause ensures that the bank
> maintains a prudent balance between risk exposure and customer accessibility, aligning with regulatory requirements and
> internal risk appetite frameworks. By defining maximum LTV ratios, the bank aims to mitigate potential losses arising from
> collateral depreciation or default scenarios while fostering responsible lending practices.
> This synthetic demonstration document is designed to illustrate how LTV ceilings are structured within a broader credit policy
> framework. It provides a realistic example of how thresholds, roles, and controls are integrated to create a robust underwriting
> process. While the data and scenarios prese… [full passage in workbook/JSON]

**Credit risk → Commercial → Unspecified product → Eligibility → Foreign currency risk**

4.2 Country Risk · version 1.0 · CPI-CLAUSE-208 · page 4 · synthetic: True

> 4. 4.2.4 Underwriting Criteria
> The bank’s underwriting criteria for country risk are designed to ensure that all credit exposures to foreign jurisdictions are
> evaluated using a consistent and rigorous methodology. The criteria are structured around a multi-dimensional assessment that
> includes political, economic, and financial factors. Each country is assigned a Country Risk Rating (CRR) on a scale of 1 to 10,
> with 1 representing the lowest risk and 10 the highest. The CRR is a composite score derived from both quantitative indicators
> and qualitative judgments.
> Quantitative indicators include macroeconomic metrics such as GDP growth, inflation rates, fiscal balance, current account
> balance, and external debt levels. These indicators are sourced from reputable third-party providers, such as the International
> Monetary Fund (IMF), World Bank, or commercial risk rating agencies. The bank sup… [full passage in workbook/JSON]

**Credit risk → Commercial → Unspecified product → Approval authority → Recovery and special assets**

2.1 Coverage Ratios · version 2.4 · CPI-CLAUSE-232 · page 6 · synthetic: True

> 6. 6. Approval Authorities and Escalation Paths
> Approval authorities for coverage ratio exceptions are structured to ensure that deviations from policy are appropriately
> reviewed and authorized. Underwriters are empowered to approve credit applications that meet all coverage ratio thresholds
> without further escalation. However, any application where a coverage ratio falls below the minimum threshold but remains
> above the warning level must be escalated to the Head of Underwriting for approval.
> If a coverage ratio falls below the warning level but remains above the breach level, approval must be obtained from the CCO.
> In such cases, the underwriter must provide a detailed rationale for the deviation, including an analysis of mitigating factors and
> a corrective action plan. The CCO may impose additional covenants or monitoring requirements as a condition of approval.
> Coverage ratios that f… [full passage in workbook/JSON]

**Credit risk → Enterprise → Unspecified product → Purpose and objectives → Spread and RAROC**

1.1 RAROC Floors · version 1.7 · CPI-CLAUSE-282 · page 1 · synthetic: True

> 1. 1. Purpose and Objectives
> This synthetic demonstration document, titled '1.1 RAROC Floors,' establishes the Risk-Adjusted Return on Capital (RAROC)
> floors for credit transactions under the parent policy PRC-v1.7. The purpose of this policy is to ensure that all credit exposures
> generate returns commensurate with their risk, aligning with the bank’s strategic objectives of sustainable profitability and
> risk-adjusted performance optimization. By setting explicit RAROC floors, the bank aims to prevent the erosion of economic
> value through suboptimal risk-taking and to foster a culture of disciplined credit origination and portfolio management.
> The primary objective of this policy is to define minimum acceptable RAROC thresholds for various credit asset classes,
> ensuring that each transaction or portfolio segment contributes positively to the bank’s economic profit. These thresholds are
> d… [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Reporting → Non-performing loans**

3.1 Approval Authorities · version 3.3 · CPI-CLAUSE-379 · page 9 · synthetic: True

> 9. 9. Reporting
> The synthetic credit policy mandates comprehensive reporting to ensure transparency, accountability, and informed
> decision-making. Reports are generated at various frequencies and distributed to relevant stakeholders, including senior
> management, the Credit Committee, and the Board of Directors.
> Monthly credit reports provide an overview of the bank’s credit portfolio, including new approvals, disbursements, repayments,
> and any breaches of limits or underwriting criteria. These reports include key metrics such as portfolio concentration, credit
> quality trends, and the status of exceptions and escalations. The reports are prepared by the Credit Risk Management Team
> and reviewed by the CCO before distribution.
> Quarterly reports focus on the performance of the credit portfolio, including delinquency rates, non-performing loans (NPLs),
> and provisions for credit losses. These … [full passage in workbook/JSON]

**Credit risk → Unspecified area → Unspecified product → Purpose and objectives → Days past due**

POL-71 Delinquency Management Policy · version 1.0 · CPI-CLAUSE-453 · page not recorded · synthetic: True

> Define early delinquency identification, aging, segmentation, contact, cure, escalation and reporting controls.

**Credit risk → Unspecified area → Unspecified product → Remediation and recovery → Hardship and forbearance**

POL-71 Delinquency Management Policy · version 1.0 · CPI-CLAUSE-490 · page not recorded · synthetic: True

> Temporary hardship, dispute, fraud and operational errors shall be distinguished from unwillingness to pay.

**Credit risk → Unspecified area → Unspecified product → Remediation and recovery → Write-off**

POL-75 Non-Performing Loan (NPL) Policy · version 1.0 · CPI-CLAUSE-942 · page not recorded · synthetic: True

> Write-off shall not automatically end recovery activity or legal rights.

**Credit risk → Unspecified area → Unspecified product → Definitions → Debt sale**

POL-80 Debt Sale Policy · version 1.0 · CPI-CLAUSE-1454 · page not recorded · synthetic: True

> Debt sale | Transfer of credit rights or economic interest to a buyer.

## Source inventory

| Policy | Version | Passages | Synthetic | Source state |
|---|---|---:|---|---|
| 4.1 Underwriting Standards | 4.2 | 20 | True | CURRENT |
| 4.2 Leverage Limits | 4.2 | 21 | True | CURRENT |
| 4.3 Tenor Limits | 4.2 | 20 | True | CURRENT |
| 4.4 Covenant Package | 4.2 | 21 | True | CURRENT |
| 3.1 DSCR Minimums | 3.1 | 20 | True | CURRENT |
| 3.2 LTV Ceilings | 3.1 | 20 | True | CURRENT |
| 1.1 Enterprise Limits | 1.0 | 20 | True | CURRENT |
| 3.5 Sector Concentration | 1.0 | 20 | True | CURRENT |
| 4.2 Country Risk | 1.0 | 20 | True | CURRENT |
| 2.1 Coverage Ratios | 2.4 | 20 | True | CURRENT |
| 2.2 Eligible Collateral | 2.4 | 20 | True | CURRENT |
| 2.3 Haircuts | 2.4 | 20 | True | CURRENT |
| 1.1 RAROC Floors | 1.7 | 21 | True | CURRENT |
| 1.2 Spread Grid | 1.7 | 20 | True | CURRENT |
| 2.1 CRE Sub-sector Limits | 2.0 | 20 | True | CURRENT |
| 2.2 Construction Guidance | 2.0 | 20 | True | CURRENT |
| 3.1 Approval Authorities | 3.3 | 20 | True | CURRENT |
| 3.2 Escalation Rules | 3.3 | 21 | True | CURRENT |
| A.1 RWA Treatment | Basel IV | 20 | True | CURRENT |
| A.2 Capital Floors | Basel IV | 21 | True | CURRENT |
| POL-71 Delinquency Management Policy | 1.0 | 110 | True | CURRENT |
| POL-72 Collections Policy | 1.0 | 110 | True | CURRENT |
| POL-73 Hardship & Forbearance Policy | 1.0 | 110 | True | CURRENT |
| POL-74 Restructuring & Modification Policy | 1.0 | 110 | True | CURRENT |
| POL-75 Non-Performing Loan (NPL) Policy | 1.0 | 110 | True | CURRENT |
| POL-76 Watchlist & Special Mention Policy | 1.0 | 110 | True | CURRENT |
| POL-77 Special Assets Management Policy | 1.0 | 110 | True | CURRENT |
| POL-78 Recovery Policy | 1.0 | 110 | True | CURRENT |
| POL-79 Write-Off Policy | 1.0 | 110 | True | CURRENT |
| POL-80 Debt Sale Policy | 1.0 | 112 | True | CURRENT |
| Credit Rating Standards | 1.0 | 22 | True | CURRENT |
| Industry Risk Assessment Policy | 1.0 | 20 | True | CURRENT |
| Foreign Currency Credit Risk Policy | 1.0 | 20 | True | CURRENT |
| Credit Duration Risk Policy | 1.0 | 20 | True | CURRENT |
| Credit Portfolio Liquidity Policy | 1.0 | 20 | True | CURRENT |
