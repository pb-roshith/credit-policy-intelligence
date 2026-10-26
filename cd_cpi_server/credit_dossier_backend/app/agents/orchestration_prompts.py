"""
Orchestration Prompts — fixed system prompt + 16 section-specific user prompts.

The orchestration agent is a single Mistral Agent (mistral-large-latest) with a
fixed system prompt. For each section, a dynamic user prompt is sent that describes
what documents and data the section needs.

The agent analyzes MCP document summaries and returns a structured JSON strategy
that the section agent uses to guide its library search.
"""

from __future__ import annotations

# ── Fixed System Prompt (set as agent instructions at creation) ──────────

ORCHESTRATION_SYSTEM_PROMPT = """\
You are a Credit Dossier Document Orchestrator at a leading commercial bank.

ROLE:
You analyze available document summaries and determine which documents are most
relevant for generating a specific section of a credit pitch book.

WORKFLOW:
1. Read the SECTION REQUIREMENTS to understand what data the section needs.
2. Analyze the AVAILABLE DOCUMENT SUMMARIES to identify relevant sources.
3. Match documents to the section's specific data requirements.
4. Output a structured JSON strategy.

OUTPUT FORMAT — Return ONLY a valid JSON object, nothing else:
{
    "recommended_documents": [
        {"title": "<document name>", "relevance": "<why needed>", "priority": "high|medium|low"}
    ],
    "priority_data_points": ["<specific data point 1>", "<specific data point 2>"],
    "search_queries": ["<search query for library>", "<another search query>"],
    "confidence": <float 0.0 to 1.0>,
    "gaps": ["<missing data type 1>", "<missing data type 2>"],
    "strategy_summary": "<2-3 sentence strategy for the section agent>"
}

RULES:
1. Only recommend documents that GENUINELY contain relevant data for the section.
2. Rank by relevance — most important documents first with priority "high".
3. Be specific about what data points to extract from each document.
4. If no documents match, return empty recommended_documents with confidence=0.
5. The search_queries should help the section agent find relevant passages in its document library.
6. Consider that manually uploaded documents in the Mistral Library may also be available beyond what is shown in summaries.
7. Return ONLY the JSON object. No markdown fences, no explanation outside JSON.
8. Never fabricate document titles — only reference documents from the summaries provided.
"""


# ── Section-Specific User Prompt Templates ──────────────────────────────
# Each template has {deal_context} and {document_summaries} placeholders.

SECTION_USER_PROMPTS: dict[str, str] = {

    "executive_summary": """\
SECTION: Executive Summary
DESCRIPTION: High-level overview of client, facility, and credit recommendation.

INPUT SOURCES: CRM data, annual reports, financial summaries, credit rating reports, \
management presentations, internal credit approval notes

EXPECTED OUTPUT: Concise deal summary covering borrower profile, proposed facility, \
credit recommendation, key financial highlights, and risk-reward snapshot.

KEY INFORMATION NEEDED:
- Revenue, EBITDA, PAT, net worth (latest year)
- Credit ratings (internal and external) with outlook
- Business overview and industry positioning
- Proposed facility details (amount, tenor, pricing, security)
- Key credit strengths (3-5 bullet points)
- Risk snapshot with top 2-3 risks and mitigants
- Relationship vintage and track record with the bank
- Collateral/security summary and coverage
- Compliance with credit policy norms

PRIORITY DOCUMENT TYPES: Annual reports, financial summaries, credit rating reports, \
CRM/relationship data, management presentations, term sheets

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents that provide a comprehensive overview for the Executive Summary. \
Prioritize documents with financial highlights, credit ratings, and business overview.""",


    "client_overview": """\
SECTION: Client Overview (Mandatory)
DESCRIPTION: Company profile, ownership, and management assessment.

INPUT SOURCES: CRM, client website, annual reports, external databases (Capital IQ, MCA filings)

EXPECTED OUTPUT: Structured company profile and narrative covering business model, \
ownership, and management quality.

KEY INFORMATION NEEDED:
- Business overview: products/services sold by the company
- Business model: online, trading, wholesale, manufacturing, etc.
- Ownership structure: parent company, subsidiary details, major shareholders
- Country of business: revenue contribution by geography, headquarters location
- Strategic acquisitions made in the last 2-3 years
- Key management personnel and any recent changes in management
- Business segment composition and revenue contribution by segment
- Top customers and suppliers (concentration risk)
- Company history, incorporation date, legal entity details
- Group structure (parent, subsidiaries, associates)
- Governance structure and board composition

PRIORITY DOCUMENT TYPES: Company registration docs, annual reports (company info sections), \
KYC documents, CRM records, management bios, public filings (MCA), Capital IQ data

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents containing company background, business model details, ownership structure, \
management profiles, segment composition, and group structure. Prioritize annual reports \
and CRM data for comprehensive company profiling.""",


    "relationship_summary": """\
SECTION: Relationship Summary (Existing Clients) (Mandatory)
DESCRIPTION: Historical exposure, banking relationship, and facility utilization analysis.

INPUT SOURCES: Core Banking System, RWA data, limits and utilization reports

EXPECTED OUTPUT: Summary of existing facilities, utilization trends, relationship history, \
and cross-sell opportunities.

KEY INFORMATION NEEDED:
- Exposure through loans/investments over the last 3 years
- Changes in exposure over time (trend analysis)
- Credit losses or delinquencies in the relationship
- Current deposit balances held with the bank
- Customer tenure with the bank (relationship vintage)
- Key banking products used by the customer
- Limits, utilization, and collateral details for each facility
- Covenant breaches (if any) in existing facilities
- Account conduct (overdue history, LC devolvement, cheque bounces)
- Wallet share trends (current vs. potential)
- Revenue generated from the relationship
- Peer bank exposure and consortium details
- Cross-sell opportunities identified

PRIORITY DOCUMENT TYPES: CRM data, Core Banking System extracts, transaction history, \
account statements, relationship/RM reports, internal banking records, RWA data

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with banking relationship data, exposure history, facility utilization, \
account conduct, and existing facilities. Prioritize Core Banking System data and \
relationship reports for comprehensive relationship profiling.""",


    "industry_analysis": """\
SECTION: Industry Analysis (Mandatory)
DESCRIPTION: Industry trends, competitive positioning, and outlook assessment.

INPUT SOURCES: External market data, industry reports, news feeds

EXPECTED OUTPUT: AI-generated industry overview including growth outlook, \
customer positioning, and key risks.

KEY INFORMATION NEEDED:
- Industry classification/mapping for the customer
- Expected industry growth and performance over the next 2-3 years
- Customer's position within the industry (market share, ranking)
- Key industry growth drivers (demand trends, policy support, technology shifts)
- Major industry risks (regulatory changes, cyclicality, disruption threats)
- Industry cycle position (expansion/peak/contraction)
- Competitive landscape and key players
- Market size, growth rates, and CAGR
- Regulatory environment and upcoming policy changes
- Demand-supply dynamics and pricing trends

PRIORITY DOCUMENT TYPES: Industry/sector reports, rating agency sector notes, \
market research, annual reports (industry sections), IBEF reports, news feeds

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with industry classification, growth outlook, competitive landscape, \
and sector risks. Prioritize recent industry reports and rating agency sector notes \
for forward-looking industry assessment.""",


    "financial_analysis": """\
SECTION: Financial Analysis (Mandatory)
DESCRIPTION: Three-year financial trend analysis with key drivers.

INPUT SOURCES: Audited financial statements, annual reports, quarterly results, \
MIS data, management accounts, projected financials

EXPECTED OUTPUT: Comprehensive financial trend analysis with tabular P&L snapshot, \
balance sheet strength assessment, and working capital analysis.

KEY INFORMATION NEEDED:
- Revenue, EBITDA, PAT across 3+ years with YoY growth rates
- Revenue breakdown by segment/product and geographic contribution
- EBITDA margins and PAT margins trend with variance analysis
- Net worth, total debt, debt-equity ratio over 3 years
- Working capital metrics (debtors, inventory, creditors in days)
- Capital expenditure and investment patterns
- Balance sheet composition (assets, liabilities, equity)
- Exceptional/one-off items impacting reported financials
- Segmental profitability analysis
- Projected financials (if available) for next 2-3 years

PRIORITY DOCUMENT TYPES: Audited financial statements, annual reports, quarterly results, \
MIS data, management accounts, projected financials

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with detailed financial statements and P&L data across multiple years. \
Prioritize audited financials over management accounts. Look for segmental breakdowns \
and projected financials for forward-looking analysis.""",


    "ratio_analysis": """\
SECTION: Ratio Analysis (Mandatory)
DESCRIPTION: Key financial ratios across leverage, coverage, liquidity, profitability.

INPUT SOURCES: Financial statements, ratio computation sheets, rating reports, \
bank analysis sheets, industry benchmark data

EXPECTED OUTPUT: Multi-year ratio trend table with commentary on leverage health, \
coverage adequacy, liquidity position, and profitability benchmarks.

KEY INFORMATION NEEDED:
- Leverage ratios: D/E, TOL/TNW, Debt/EBITDA across 3+ years
- Coverage ratios: ICR, DSCR across 3+ years
- Liquidity ratios: Current ratio, Quick ratio
- Profitability ratios: ROCE, ROE, EBITDA margin, PAT margin
- Efficiency ratios: Debtor days, Inventory days, Creditor days
- Industry benchmark ratios for peer comparison
- Ratio trends and direction (improving/deteriorating)
- Covenant ratio thresholds (if applicable)
- Rating agency ratio observations and triggers

PRIORITY DOCUMENT TYPES: Financial statements, ratio computation sheets, \
rating reports (ratio sections), bank analysis sheets, industry benchmark data

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents containing computed financial ratios or raw data to compute them. \
Prioritize rating reports that include ratio analysis and industry benchmarks \
for peer comparison.""",


    "cash_flow_analysis": """\
SECTION: Cash Flow Analysis (Mandatory)
DESCRIPTION: Operating, investing, financing cash flows and repayment capacity.

INPUT SOURCES: Cash flow statements, financial statements, DSCR computations, \
projected financials, debt repayment schedules

EXPECTED OUTPUT: Multi-year cash flow trend analysis with CFO quality assessment, \
free cash flow computation, DSCR adequacy, and repayment capacity verdict.

KEY INFORMATION NEEDED:
- Cash flow from operations (CFO) across 3+ years with quality assessment
- Cash flow from investing (CFI): capex, acquisitions, divestments
- Cash flow from financing (CFF): debt raised/repaid, equity, dividends
- Free cash flow computation and trend
- CFO/EBITDA conversion ratio (cash quality indicator)
- DSCR computation and adequacy assessment
- Projected cash flows for next 2-3 years (if available)
- Debt repayment schedule (maturity profile)
- Working capital changes impacting CFO
- Dividend payout trends and sustainability

PRIORITY DOCUMENT TYPES: Cash flow statements, financial statements, \
DSCR computations, projected financials, debt schedules

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with cash flow statements and DSCR data. \
Projected financials are highly valuable for repayment capacity assessment. \
Prioritize audited cash flow statements over management projections.""",


    "qualitative_assessment": """\
SECTION: Qualitative Assessment
DESCRIPTION: Management quality, governance, business sustainability assessment.

INPUT SOURCES: RM/relationship notes, KYC documents, governance reports, \
annual reports (governance sections), ESG reports, public filings, news articles

EXPECTED OUTPUT: Qualitative scorecard covering management quality, governance \
practices, business sustainability, key-person risk, and compliance track record.

KEY INFORMATION NEEDED:
- Management quality, experience, and track record
- Corporate governance practices and board composition
- Succession planning and key-person dependency risk
- Business sustainability and competitive moat assessment
- Regulatory compliance history and any penalties/violations
- Stakeholder and labour relations quality
- Technology and operational infrastructure maturity
- Brand strength and market reputation
- Related party transactions and group dependencies
- Audit observations and qualifications (if any)

PRIORITY DOCUMENT TYPES: RM/relationship notes, KYC documents, governance reports, \
annual reports (governance sections), ESG reports, public filings, news

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with qualitative data on management, governance, and business quality. \
Prioritize RM notes and governance reports for first-hand management assessment.""",


    "credit_risk_assessment": """\
SECTION: Credit Risk Assessment (Mandatory)
DESCRIPTION: Internal rating, external ratings, and risk drivers.

INPUT SOURCES: Internal rating model outputs, credit rating reports (CRISIL/ICRA/CARE/Fitch/Moody's), \
risk assessment sheets, RBI guidelines, risk register

EXPECTED OUTPUT: Credit risk profile with internal/external ratings, key risk drivers \
ranked by severity, rating triggers, and risk-adjusted return assessment.

KEY INFORMATION NEEDED:
- Internal credit rating and risk grade with rationale
- External ratings (CRISIL/ICRA/CARE/Fitch/Moody's) with outlook and date
- Key risk drivers (top 5) with severity and likelihood
- Rating triggers and watchlist items
- Risk migration history (upgrade/downgrade trajectory)
- PD/LGD/Expected loss computations (if available)
- Risk-adjusted return on capital (RAROC) assessment
- Sector-specific risk factors
- Counterparty credit risk assessment
- Regulatory risk classification (standard/SMA/NPA)

PRIORITY DOCUMENT TYPES: Internal rating model outputs, credit rating reports, \
risk assessment sheets, RBI guidelines, risk register

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with credit ratings, risk assessments, and rating rationale. \
Prioritize recent external rating reports and internal risk model outputs.""",


    "facility_structure": """\
SECTION: Facility Structure (Mandatory)
DESCRIPTION: Complete facility terms, sub-limits, pricing, and conditions.

INPUT SOURCES: Term sheets, deal sheets, sanction letters, facility agreements, \
internal credit approval notes

EXPECTED OUTPUT: Structured facility terms table covering type, limits, tenor, \
pricing, repayment schedule, conditions, and end-use of funds.

KEY INFORMATION NEEDED:
- Facility type (term loan, working capital, LC/BG, etc.) and total limit
- Sub-limit structure and interchangeability provisions
- Tenor and detailed repayment schedule (quarterly/monthly/bullet)
- Pricing structure: base rate + spread, reset frequency, fee structure
- Moratorium period (if any)
- Conditions precedent and subsequent
- End-use of funds with purpose justification
- Drawing power and margin requirements
- Prepayment provisions and penalties
- Fee structure (processing, commitment, documentation fees)

PRIORITY DOCUMENT TYPES: Term sheets, deal sheets, sanction letters, \
facility agreements, internal credit approval notes

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with facility terms, pricing, and deal structure details. \
Prioritize term sheets and sanction letters for definitive facility terms.""",


    "policy_mapping": """\
SECTION: Policy Mapping (Mandatory)
DESCRIPTION: Mapping deal against credit policy parameters and regulatory norms.

INPUT SOURCES: Credit policy documents, lending guidelines, regulatory circulars, \
internal norms, deviation approval notes

EXPECTED OUTPUT: Policy compliance matrix showing each parameter, norm, actual value, \
compliance status, and deviations with justification.

KEY INFORMATION NEEDED:
- Credit policy parameter thresholds for the relevant segment/sector
- Exposure norms: sector caps, group exposure limits, single borrower limits
- Rating thresholds required for approval authority
- Policy deviations identified with detailed justification
- Delegation of authority (DOA) mapping for the proposed exposure
- Regulatory compliance check (RBI/NHB/SEBI as applicable)
- Exposure concentration analysis (sector, group, geography)
- Minimum collateral coverage requirements per policy
- Tenor and pricing norms compliance
- Priority sector classification and PSL applicability

PRIORITY DOCUMENT TYPES: Credit policy documents, lending guidelines, \
regulatory circulars, internal norms, deviation approval notes

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with credit policy norms, regulatory guidelines, and deviation records. \
Prioritize the latest credit policy document and any regulatory circulars.""",


    "collateral_and_security": """\
SECTION: Collateral and Security (Mandatory)
DESCRIPTION: Security package, valuation, insurance, and charge details.

INPUT SOURCES: Valuation reports, security documents, property records, \
insurance policies, charge creation documents, guarantee deeds

EXPECTED OUTPUT: Complete security package with valuation details, security cover \
computation, insurance adequacy, and charge creation status.

KEY INFORMATION NEEDED:
- Primary security details (description, location, ownership)
- Collateral security details (type, description, value)
- Asset valuations with independent valuer certification and date
- Security cover ratio computation (value/exposure)
- Insurance coverage details and adequacy assessment
- Charge type for each security (mortgage/hypothecation/pledge)
- Personal and corporate guarantee details
- Priority of charge (first/second/pari-passu)
- CERSAI registration status
- Forced sale value vs. market value assessment

PRIORITY DOCUMENT TYPES: Valuation reports, security documents, property records, \
insurance policies, charge creation documents, guarantee deeds

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with collateral valuations, security details, and insurance data. \
Prioritize independent valuation reports and charge creation documents.""",


    "covenants_and_conditions": """\
SECTION: Covenants and Conditions (Mandatory)
DESCRIPTION: Financial and non-financial covenants with thresholds.

INPUT SOURCES: Term sheets, sanction letters, covenant schedules, \
facility agreements, historical compliance reports

EXPECTED OUTPUT: Comprehensive covenant schedule with financial/non-financial covenants, \
thresholds, testing frequency, event of default triggers, and compliance history.

KEY INFORMATION NEEDED:
- Financial covenants: specific ratio thresholds and testing frequency
- Non-financial covenants and reporting requirements (frequency, format)
- Negative covenants: restrictions on dividend, capex, additional debt
- Event of default triggers and acceleration clauses
- Cure periods and grace periods for covenant breaches
- Historical covenant compliance record (pass/fail by period)
- Affirmative covenants and information covenants
- Cross-default provisions with other lenders
- Material adverse change (MAC) clause terms

PRIORITY DOCUMENT TYPES: Term sheets, sanction letters, covenant schedules, \
facility agreements, historical compliance reports

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with covenant schedules, compliance records, and facility terms. \
Prioritize sanction letters and term sheets for definitive covenant terms.""",


    "esg_analysis": """\
SECTION: ESG Analysis
DESCRIPTION: Environmental, Social, and Governance risk assessment.

INPUT SOURCES: ESG/sustainability reports, environmental assessments, \
social audit reports, governance reports, ESG rating agency data

EXPECTED OUTPUT: ESG scorecard with environmental, social, and governance \
assessment, material risks, external ratings, and improvement recommendations.

KEY INFORMATION NEEDED:
- Environmental: carbon emissions, energy consumption, waste management, climate risk exposure
- Social: labour practices, employee welfare, community impact, diversity metrics, human rights
- Governance: board composition and independence, transparency, ethics policies, compliance
- ESG ratings/scores from external agencies (MSCI, Sustainalytics, etc.)
- Material ESG risks specific to the industry/sector
- ESG-linked pricing or financing opportunities
- Regulatory ESG requirements and compliance status
- ESG controversies or adverse media (if any)
- Carbon transition risk assessment for the sector

PRIORITY DOCUMENT TYPES: ESG/sustainability reports, environmental assessments, \
social audit reports, governance reports, ESG rating agency data

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents with ESG data, sustainability metrics, and governance details. \
Prioritize company sustainability reports and external ESG ratings.""",


    "key_risks_and_mitigants": """\
SECTION: Key Risks and Mitigants (Mandatory)
DESCRIPTION: Top risks ranked by severity with mitigation strategies.

INPUT SOURCES: Risk registers, credit assessment reports, industry reports, \
financial statements, internal risk analysis, rating reports

EXPECTED OUTPUT: Risk register with top 5-8 risks ranked by severity, each with \
description, likelihood, impact, mitigant, and residual risk assessment.

KEY INFORMATION NEEDED:
- Business risks: market volatility, competition intensity, customer/supplier concentration
- Financial risks: liquidity stress, leverage levels, forex exposure, interest rate sensitivity
- Industry risks: cyclicality, regulatory changes, technological disruption
- Management risks: key-person dependency, succession gaps, governance weaknesses
- Operational risks: technology failures, supply chain disruptions, execution delays
- Risk severity assessment: High/Medium/Low rating for each risk
- Risk likelihood and potential impact quantification
- Existing mitigants for each identified risk
- Residual risk assessment after mitigants
- Stress scenario outcomes (downside/worst case)

PRIORITY DOCUMENT TYPES: Risk registers, credit assessment reports, industry reports, \
financial statements, internal risk analysis, rating reports

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select documents that highlight risks, challenges, and mitigating factors. \
Prioritize rating reports and internal risk assessments for structured risk data.""",


    "appendix": """\
SECTION: Appendix
DESCRIPTION: Supporting tables, schedules, and reference data.

INPUT SOURCES: All available documents — financial statements, supporting data, \
reference tables, workpapers

EXPECTED OUTPUT: Supplementary tables, schedules, glossary, and document index \
that support the main dossier sections.

KEY INFORMATION NEEDED:
- Supplementary financial schedules (depreciation, borrowing details, etc.)
- Additional data tables not covered in main sections
- Glossary of key terms and abbreviations used in the dossier
- Document index with list of all source documents referenced
- Supporting analysis and workpapers
- Detailed assumptions for projections (if any)
- Organizational charts and group structure diagrams
- Regulatory filing extracts and compliance certificates

PRIORITY DOCUMENT TYPES: All available documents — any supplementary data tables, \
financial schedules, reference materials

{deal_context}

--- Available Document Summaries ---
{document_summaries}

Select any documents with supplementary data, reference tables, or additional details \
that complement the main dossier sections.""",
}


def build_orchestration_user_prompt(
    section_key: str,
    deal_context: str,
    document_summaries: str,
) -> str:
    """
    Build the dynamic user prompt for the orchestration agent.

    Args:
        section_key: The section being generated (e.g. "executive_summary")
        deal_context: Pre-built deal context string (section-specific fields)
        document_summaries: Document summaries from MCP server

    Returns:
        Formatted user prompt string
    """
    template = SECTION_USER_PROMPTS.get(section_key)
    if not template:
        # Fallback for unknown sections
        template = (
            "SECTION: {section_key}\n"
            "Select the most relevant documents for this credit dossier section.\n\n"
            "{deal_context}\n\n"
            "--- Available Document Summaries ---\n"
            "{document_summaries}"
        )
        return template.format(
            section_key=section_key,
            deal_context=deal_context,
            document_summaries=document_summaries,
        )

    return template.format(
        deal_context=deal_context,
        document_summaries=document_summaries or "No document summaries available.",
    )
