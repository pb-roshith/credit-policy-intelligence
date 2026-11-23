"""The 17 PDF sources and 16 PostgreSQL credit-table definitions."""

from __future__ import annotations

import re
from datetime import date, timedelta
from random import Random


PDF_FILES = (
    "Asset_Details.pdf",
    "Certificate_of_Incorporation.pdf",
    "Company_Profile.pdf",
    "Declarations.pdf",
    "Existing_Loan_Details.pdf",
    "GST_Registration.pdf",
    "GST_Returns.pdf",
    "Income_Tax_Returns_3_Years.pdf",
    "Key_Customers_Suppliers.pdf",
    "KYC_Credit_Reports.pdf",
    "KYC_Identity_Proofs.pdf",
    "KYC_Income_Tax_Returns.pdf",
    "Litigation_Details.pdf",
    "MOA_AOA.pdf",
    "PAN_Card.pdf",
    "Property_Documents.pdf",
    "Purpose_of_Loan.pdf",
)

TABLE_NAMES = (
    "credit_dossier.credit_balance_sheet",
    "credit_dossier.credit_cashflow_statement",
    "credit_dossier.credit_income_statement",
    "credit_dossier.credit_bank_statements",
    "credit_dossier.credit_net_worth_statement",
    "credit_dossier.credit_projected_financials",
    "credit_dossier.section2_customer_information",
    "credit_dossier.section2_ownership_structure",
    "credit_dossier.section3_customer_financial_information_historical",
    "credit_dossier.section3a_financial_forecast",
    "credit_dossier.section3a_customer_facilities",
    "credit_dossier.section3a_other_financial_institution_exposure",
    "credit_dossier.section3a_collateral_guarantee_information",
    "credit_dossier.section3b_documentation_security_exceptions",
    "credit_dossier.section3b_covenant_description",
    "credit_dossier.section3b_credit_committee_resolution",
)

# Business columns exposed directly in PostgreSQL. The JSONB payload is retained
# for forward compatibility, while these columns make each table useful to SQL
# analysts without JSON operators.
TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    TABLE_NAMES[0]: (
        "particular", "prior_year_2", "prior_year", "current_year",
        "variance_pct", "commentary",
    ),
    TABLE_NAMES[1]: (
        "particular", "prior_year_2", "prior_year", "current_year",
        "cashflow_classification", "commentary",
    ),
    TABLE_NAMES[2]: (
        "particular", "prior_year_2", "prior_year", "current_year",
        "margin_pct", "commentary",
    ),
    TABLE_NAMES[3]: (
        "transaction_date", "opening_balance", "credits", "debits",
        "closing_balance", "inward_return_count", "remarks",
    ),
    TABLE_NAMES[4]: (
        "particular", "book_value", "market_value", "ownership",
        "encumbrance", "valuation_date", "valuer",
    ),
    TABLE_NAMES[5]: (
        "particular", "forecast_year_1", "forecast_year_2",
        "forecast_year_3", "assumption", "sensitivity",
    ),
    TABLE_NAMES[6]: (
        "business_activities", "business_since", "relationship_status",
        "regulator_enquiry_date", "regulator_enquiry_note",
        "current_rating", "current_rating_date", "current_rating_note",
        "previous_rating", "previous_rating_date", "previous_rating_note",
        "bank_internal_rating", "blacklisted", "blacklisted_note",
        "related_party_status", "related_party_type",
        "politically_exposed_person", "pep_note",
        "present_in_defaulter_list", "defaulter_list_note",
        "source_pdf_pages",
    ),
    TABLE_NAMES[7]: (
        "owner_details", "capital_amount", "ownership_percent",
        "owner_type", "board_rights", "source_note", "source_pdf_pages",
    ),
    TABLE_NAMES[8]: (
        "statement_year", "statement_date", "statement_period_months",
        "audit_method", "external_auditor", "currency_code", "unit_scale",
        "sales_turnover", "sales_growth_pct", "gross_margin_pct",
        "net_operating_profit", "net_profit_before_tax_sales_pct",
        "net_profit", "ebitda", "net_cash_after_operations", "net_worth",
        "bank_borrowing", "total_liability", "total_assets",
        "debt_tangible_net_worth_pct", "accounts_receivable_days",
        "accounts_payable_days", "inventory_days", "interest_coverage",
        "source_pdf_pages", "data_quality_note",
    ),
    TABLE_NAMES[9]: (
        "forecast_year", "forecast_label", "currency_code", "unit_scale",
        "sales_turnover", "sales_growth_pct", "gross_margin_pct",
        "net_operating_profit", "net_profit_before_tax_sales_pct",
        "net_profit", "ebitda", "net_cash_after_operations", "net_worth",
        "bank_borrowing", "total_liability", "total_assets",
        "debt_tangible_net_worth_pct", "accounts_receivable_days",
        "accounts_payable_days", "inventory_days", "interest_coverage",
        "model_name", "model_note", "source_table",
    ),
    TABLE_NAMES[10]: (
        "facility_type", "facility_amount_existing", "utilization",
        "facility_amount_new", "currency_code", "unit_scale", "pricing",
        "tenure", "repayment", "purpose", "source_note",
    ),
    TABLE_NAMES[11]: (
        "exposure_type", "lender", "exposure_limit", "exposure",
        "security", "currency_code", "unit_scale", "repayment_status",
        "source_note",
    ),
    TABLE_NAMES[12]: (
        "collateral_category", "mitigant_type", "description", "amount",
        "currency_code", "unit_scale", "valuation_date", "valuer",
        "haircut_pct", "eligible_value", "source_note",
    ),
    TABLE_NAMES[13]: (
        "exception_code", "end_date", "mitigant_exception_description",
        "exception_severity", "status", "owner", "action_plan",
        "source_note",
    ),
    TABLE_NAMES[14]: (
        "covenant_type", "reporting_date", "due_date", "description",
        "threshold_value", "reported_value", "compliance_status",
        "testing_frequency", "source_pdf_pages", "source_note",
    ),
    TABLE_NAMES[15]: (
        "credit_committee_name", "decision", "resolution_by",
        "meeting_date", "meeting_no", "resolution_summary",
        "conditions_precedent", "conditions_subsequent",
        "final_approving_authority", "source_note",
    ),
}

FINANCIAL_AI_TABLES = TABLE_NAMES[:6]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "company"


def build_company_context(
    company_name: str,
    industry: str,
    geography: str,
) -> dict[str, object]:
    """Build deterministic, internally consistent synthetic borrower data."""
    rng = Random(f"{company_name}|{industry}|{geography}")
    current_year = date.today().year
    revenue = rng.randint(75_000, 165_000)
    ebitda = round(revenue * rng.uniform(0.13, 0.19), 2)
    net_worth = round(revenue * rng.uniform(0.32, 0.46), 2)
    requested_limit = rng.choice([7_500, 10_000, 12_500, 15_000, 18_000])
    incorporation_year = rng.randint(2008, 2020)
    return {
        "company_name": company_name,
        "industry": industry,
        "geography": geography,
        "segment": "Mid Corporate",
        "kyc_status": "Verified",
        "registered_address": (
            f"Plot {rng.randint(10, 99)}, Industrial Estate, {geography}"
        ),
        "incorporation_year": incorporation_year,
        "pan": f"ABCDE{rng.randint(1000, 9999)}F",
        "gstin": f"27ABCDE{rng.randint(1000, 9999)}F1Z{rng.randint(1, 9)}",
        "cin": (
            f"U{rng.randint(10000, 99999)}MH{incorporation_year}"
            f"PTC{rng.randint(100000, 999999)}"
        ),
        "revenue": revenue,
        "ebitda": ebitda,
        "net_worth": net_worth,
        "requested_limit": requested_limit,
        "currency": "INR",
        "customers": [
            "Tata Motors Limited",
            "Mahindra & Mahindra Limited",
            "Bharat Forge Limited",
        ],
        "suppliers": [
            "JSW Steel Limited",
            "Tata Steel Limited",
            "Hindalco Industries Limited",
        ],
        "directors": ["Ananya Rao", "Rohan Mehta", "Meera Shah"],
        "current_year": current_year,
        "synthetic": True,
    }


def document_summary(filename: str, context: dict[str, object]) -> str:
    title = filename.removesuffix(".pdf").replace("_", " ")
    return (
        f"Synthetic {title} for {context['company_name']}, covering credit-relevant "
        f"information for its {context['industry']} operations in "
        f"{context['geography']}."
    )


def document_sections(
    filename: str,
    context: dict[str, object],
) -> list[tuple[str, list[str], list[list[str]]]]:
    """Return document-specific sections for a manufactured PDF."""
    company = str(context["company_name"])
    common = [
        (
            "Executive borrower reference",
            [
                f"{company} operates in {context['industry']} across {context['geography']}.",
                "This is synthetic demonstration data and must not be treated as a real filing.",
            ],
            [
                ["Identifier", "Value"],
                ["PAN", str(context["pan"])],
                ["GSTIN", str(context["gstin"])],
                ["CIN", str(context["cin"])],
            ],
        ),
        (
            "Corporate and operating profile",
            [
                f"The company was incorporated in {context['incorporation_year']} and serves a diversified industrial customer base.",
                f"Key customers include {', '.join(context['customers'])}; critical suppliers include {', '.join(context['suppliers'])}.",
            ],
            [
                ["Attribute", "Assessment"],
                ["Business segment", str(context["segment"])],
                ["Registered address", str(context["registered_address"])],
                ["KYC status", str(context["kyc_status"])],
            ],
        ),
        (
            "Financial and facility snapshot",
            [
                "The financial snapshot is reconciled to the detailed PostgreSQL statements generated with this data pack.",
                "Amounts are synthetic INR lakh values and use a consistent borrower master context.",
            ],
            [
                ["Metric", "Amount (INR lakh)"],
                ["Revenue", f"{float(context['revenue']):,.2f}"],
                ["EBITDA", f"{float(context['ebitda']):,.2f}"],
                ["Net worth", f"{float(context['net_worth']):,.2f}"],
                ["Requested limit", f"{float(context['requested_limit']):,.2f}"],
            ],
        ),
        (
            "Credit controls and data lineage",
            [
                "Identifiers, counterparties, facilities, security and financial values are shared across all 17 documents.",
                "The data is manufactured for functional testing; analysts must not rely on it for a real credit decision.",
            ],
            [
                ["Control", "Status"],
                ["Cross-document identifiers", "Reconciled"],
                ["Financial-table linkage", "Reconciled"],
                ["Synthetic-data marking", "Applied"],
            ],
        ),
    ]
    specific: dict[str, tuple[str, list[str], list[list[str]]]] = {
        "Asset_Details.pdf": (
            "Fixed and current assets",
            ["Assets support the proposed working-capital and term-loan facilities."],
            [
                ["Asset", "Book value (INR lakh)", "Security"],
                ["Land and building", "28,600", "First-ranking mortgage"],
                ["Plant and machinery", "21,450", "Hypothecation"],
                ["Inventory and receivables", "38,400", "Floating charge"],
            ],
        ),
        "Certificate_of_Incorporation.pdf": (
            "Corporate registration",
            [f"{company} was incorporated in {context['incorporation_year']}."],
            [["Field", "Value"], ["CIN", str(context["cin"])], ["Status", "Active"]],
        ),
        "Company_Profile.pdf": (
            "Business profile",
            [
                f"The borrower manufactures products in the {context['industry']} sector.",
                f"FY revenue is approximately INR {context['revenue']:,} lakh.",
            ],
            [["Metric", "Value"], ["Segment", "Mid Corporate"], ["KYC", "Verified"]],
        ),
        "Declarations.pdf": (
            "Borrower declarations",
            ["Management declares the manufactured submission complete for demonstration."],
            [["Declaration", "Response"], ["Material defaults", "None"], ["PEP", "No"]],
        ),
        "Existing_Loan_Details.pdf": (
            "Existing borrowing",
            ["Existing facilities have demonstrated satisfactory repayment conduct."],
            [
                ["Facility", "Limit", "Utilisation"],
                ["Working capital", "18,500", "14,275"],
                ["Term loan", "12,500", "10,840"],
            ],
        ),
        "GST_Registration.pdf": (
            "Indirect-tax registration",
            ["The synthetic GST registration is active at the registered address."],
            [["GSTIN", "Status"], [str(context["gstin"]), "Active"]],
        ),
        "GST_Returns.pdf": (
            "GST filing trend",
            ["Reported taxable turnover is consistent with the manufactured revenue trend."],
            [["Period", "Taxable turnover"], ["FY-2", "86,250"], ["FY-1", "97,480"], ["FY", "111,650"]],
        ),
        "Income_Tax_Returns_3_Years.pdf": (
            "Income-tax returns",
            ["Three years of synthetic returns demonstrate growing taxable profit."],
            [["Year", "Taxable income"], ["FY-2", "7,695"], ["FY-1", "9,310"], ["FY", "11,300"]],
        ),
        "Key_Customers_Suppliers.pdf": (
            "Trading counterparties",
            ["Customer and supplier concentration is monitored through annual reviews."],
            [
                ["Type", "Names"],
                ["Customers", ", ".join(context["customers"])],
                ["Suppliers", ", ".join(context["suppliers"])],
            ],
        ),
        "KYC_Credit_Reports.pdf": (
            "Credit bureau and screening",
            ["No material default, blacklist, sanctions, or PEP match is manufactured."],
            [["Check", "Result"], ["Credit bureau", "Satisfactory"], ["Sanctions", "No match"]],
        ),
        "KYC_Identity_Proofs.pdf": (
            "Identity verification",
            ["Director identities are synthetically represented as verified."],
            [["Director", "Status"]] + [[name, "Verified"] for name in context["directors"]],
        ),
        "KYC_Income_Tax_Returns.pdf": (
            "Promoter tax verification",
            ["Promoter tax filings are represented as current and reconciled."],
            [["Review", "Result"], ["PAN validation", "Passed"], ["Return filing", "Current"]],
        ),
        "Litigation_Details.pdf": (
            "Litigation review",
            ["No material litigation affecting repayment capacity is manufactured."],
            [["Matter", "Status", "Exposure"], ["Routine commercial claims", "Open", "Immaterial"]],
        ),
        "MOA_AOA.pdf": (
            "Constitutional documents",
            ["The objects clause permits the stated manufacturing and financing activities."],
            [["Document", "Status"], ["MOA", "Reviewed"], ["AOA", "Reviewed"]],
        ),
        "PAN_Card.pdf": (
            "Permanent Account Number",
            ["The synthetic PAN matches all documents in this data pack."],
            [["Name", "PAN"], [company, str(context["pan"])]],
        ),
        "Property_Documents.pdf": (
            "Property and security",
            ["Title documents support a first-ranking mortgage over the primary site."],
            [["Property", "Value", "Title"], ["Manufacturing site", "28,600", "Clear"]],
        ),
        "Purpose_of_Loan.pdf": (
            "Facility purpose",
            [
                "The requested facility supports capacity expansion and incremental working capital.",
                f"Requested limit: INR {context['requested_limit']:,} lakh.",
            ],
            [["Use", "Allocation"], ["Machinery capex", "60%"], ["Working capital", "40%"]],
        ),
    }
    return common + [specific[filename]]


def table_seed_rows(context: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    """Generate a detailed, internally reconciled fallback for all 16 tables."""
    year = int(context["current_year"])
    revenue = float(context["revenue"])
    ebitda = float(context["ebitda"])
    net_worth = float(context["net_worth"])
    requested = float(context["requested_limit"])
    company = str(context["company_name"])

    def three_year_row(
        particular: str,
        current_value: float,
        commentary: str,
        *,
        growth: float = 0.12,
        extra_key: str = "variance_pct",
        extra_value: object | None = None,
    ) -> dict[str, object]:
        prior = current_value / (1 + growth)
        prior_2 = prior / (1 + growth)
        return {
            "particular": particular,
            "prior_year_2": round(prior_2, 2),
            "prior_year": round(prior, 2),
            "current_year": round(current_value, 2),
            extra_key: (
                round(growth * 100, 2) if extra_value is None else extra_value
            ),
            "commentary": commentary,
        }

    balance_sheet = [
        three_year_row("Share capital", 500, "Paid-up capital remained stable.", growth=0),
        three_year_row("Reserves and surplus", net_worth - 500, "Retained earnings strengthened tangible net worth."),
        three_year_row("Tangible net worth", net_worth, "Net worth increased through retained profits."),
        three_year_row("Long-term borrowings", requested * .72, "Includes term debt for capacity expansion.", growth=.08),
        three_year_row("Short-term bank borrowings", requested * .88, "Working-capital utilization tracks seasonal inventory.", growth=.10),
        three_year_row("Trade payables", revenue * .13, "Payables remain within negotiated supplier terms.", growth=.09),
        three_year_row("Other current liabilities", revenue * .045, "Primarily statutory dues and accrued operating costs.", growth=.07),
        three_year_row("Land and building", net_worth * .34, "Primary manufacturing property is owned.", growth=.03),
        three_year_row("Plant and machinery", net_worth * .42, "Includes recent CNC and automation additions.", growth=.15),
        three_year_row("Capital work in progress", requested * .18, "Relates to the proposed expansion line.", growth=.25),
        three_year_row("Inventory", revenue * .16, "Raw material and finished goods support the order book.", growth=.11),
        three_year_row("Trade receivables", revenue * .18, "Receivables are concentrated among investment-grade OEMs.", growth=.10),
        three_year_row("Cash and bank balances", revenue * .026, "Liquidity includes operating balances and deposits.", growth=.12),
        three_year_row("Other current assets", revenue * .055, "Includes GST credits, advances and prepaid costs.", growth=.08),
        three_year_row("Total assets", revenue * .92, "Asset growth reflects capacity expansion.", growth=.11),
    ]

    cashflow = [
        three_year_row("Profit before tax", ebitda * .68, "Profit growth follows operating leverage.", extra_key="cashflow_classification", extra_value="Operating"),
        three_year_row("Depreciation", ebitda * .13, "Higher depreciation reflects capex commissioning.", extra_key="cashflow_classification", extra_value="Non-cash"),
        three_year_row("Finance costs", ebitda * .10, "Interest remains well covered by EBITDA.", extra_key="cashflow_classification", extra_value="Operating"),
        three_year_row("Cash generated before working capital", ebitda * .91, "Core operations remain cash generative.", extra_key="cashflow_classification", extra_value="Operating"),
        three_year_row("Increase in inventories", -revenue * .018, "Inventory investment supports order growth.", extra_key="cashflow_classification", extra_value="Operating"),
        three_year_row("Increase in receivables", -revenue * .014, "Receivable growth is aligned with sales.", extra_key="cashflow_classification", extra_value="Operating"),
        three_year_row("Increase in payables", revenue * .009, "Supplier credit partly funds growth.", extra_key="cashflow_classification", extra_value="Operating"),
        three_year_row("Net cash from operating activities", ebitda * .62, "Operating cash supports scheduled debt service.", extra_key="cashflow_classification", extra_value="Operating"),
        three_year_row("Capital expenditure", -requested * .48, "Investment in machinery and automation.", extra_key="cashflow_classification", extra_value="Investing"),
        three_year_row("Net borrowings raised/(repaid)", requested * .11, "Incremental debt funds approved expansion.", extra_key="cashflow_classification", extra_value="Financing"),
        three_year_row("Interest and dividends paid", -ebitda * .14, "Distributions remain subordinate to debt service.", extra_key="cashflow_classification", extra_value="Financing"),
        three_year_row("Closing cash balance", revenue * .026, "Closing liquidity remains adequate.", extra_key="cashflow_classification", extra_value="Closing balance"),
    ]

    income_statement = [
        three_year_row("Revenue from operations", revenue, "Growth supported by domestic OEM and export orders.", extra_key="margin_pct", extra_value="100.00"),
        three_year_row("Other operating income", revenue * .018, "Includes tooling and scrap recoveries.", extra_key="margin_pct", extra_value="1.80"),
        three_year_row("Raw material consumed", -revenue * .48, "Steel and alloy inputs remain the largest cost.", extra_key="margin_pct", extra_value="48.00"),
        three_year_row("Employee benefits", -revenue * .105, "Skilled labor cost reflects capacity expansion.", extra_key="margin_pct", extra_value="10.50"),
        three_year_row("Power and fuel", -revenue * .055, "Energy intensity is monitored monthly.", extra_key="margin_pct", extra_value="5.50"),
        three_year_row("Factory and subcontracting costs", -revenue * .09, "Variable processing cost tracks volumes.", extra_key="margin_pct", extra_value="9.00"),
        three_year_row("Selling and administration", -revenue * .065, "Includes freight, warranty and overhead.", extra_key="margin_pct", extra_value="6.50"),
        three_year_row("EBITDA", ebitda, "Margin benefits from utilization and product mix.", extra_key="margin_pct", extra_value=round(ebitda / revenue * 100, 2)),
        three_year_row("Depreciation", -ebitda * .13, "Depreciation increased after asset commissioning.", extra_key="margin_pct", extra_value=round(ebitda * .13 / revenue * 100, 2)),
        three_year_row("EBIT", ebitda * .87, "Operating profit remains robust.", extra_key="margin_pct", extra_value=round(ebitda * .87 / revenue * 100, 2)),
        three_year_row("Finance costs", -ebitda * .10, "Debt cost is supported by coverage.", extra_key="margin_pct", extra_value=round(ebitda * .10 / revenue * 100, 2)),
        three_year_row("Profit before tax", ebitda * .68, "PBT growth is consistent with revenue.", extra_key="margin_pct", extra_value=round(ebitda * .68 / revenue * 100, 2)),
        three_year_row("Tax expense", -ebitda * .17, "Tax rate reflects statutory provisions.", extra_key="margin_pct", extra_value=round(ebitda * .17 / revenue * 100, 2)),
        three_year_row("Profit after tax", ebitda * .51, "PAT is retained to support growth.", extra_key="margin_pct", extra_value=round(ebitda * .51 / revenue * 100, 2)),
    ]

    bank_rows: list[dict[str, object]] = []
    running_balance = 1350.0
    start_date = date(year, 4, 1)
    for index in range(20):
        opening = running_balance
        credit = round(420 + (index % 5) * 115.35, 2)
        debit = round(365 + (index % 4) * 96.20, 2)
        returns = 1 if index in (8, 17) else 0
        running_balance = round(opening + credit - debit, 2)
        bank_rows.append(
            {
                "transaction_date": str(start_date + timedelta(days=index)),
                "opening_balance": round(opening, 2),
                "credits": credit,
                "debits": debit,
                "closing_balance": running_balance,
                "inward_return_count": returns,
                "remarks": (
                    "One inward return; subsequently regularized"
                    if returns
                    else ["OEM customer collection", "Supplier settlement", "Payroll and statutory payments", "Export realization"][index % 4]
                ),
            }
        )

    net_worth_rows = [
        {"particular": "Factory land and building", "book_value": round(net_worth * .34, 2), "market_value": round(net_worth * .43, 2), "ownership": "Company owned", "encumbrance": "First-ranking mortgage", "valuation_date": f"{year}-03-15", "valuer": "Independent Registered Valuers LLP"},
        {"particular": "Plant and machinery", "book_value": round(net_worth * .42, 2), "market_value": round(net_worth * .48, 2), "ownership": "Company owned", "encumbrance": "Exclusive hypothecation", "valuation_date": f"{year}-03-15", "valuer": "Independent Registered Valuers LLP"},
        {"particular": "Commercial vehicles", "book_value": round(net_worth * .035, 2), "market_value": round(net_worth * .041, 2), "ownership": "Company owned", "encumbrance": "Vehicle finance charge", "valuation_date": f"{year}-03-15", "valuer": "Management estimate"},
        {"particular": "Quoted investments", "book_value": round(net_worth * .025, 2), "market_value": round(net_worth * .029, 2), "ownership": "Company owned", "encumbrance": "Nil", "valuation_date": f"{year}-03-31", "valuer": "Market quotation"},
        {"particular": "Fixed deposits", "book_value": round(net_worth * .04, 2), "market_value": round(net_worth * .04, 2), "ownership": "Company owned", "encumbrance": "Lien for bank guarantees", "valuation_date": f"{year}-03-31", "valuer": "Bank confirmation"},
        {"particular": "Promoter residential property", "book_value": round(net_worth * .10, 2), "market_value": round(net_worth * .15, 2), "ownership": "Promoter owned", "encumbrance": "Proposed collateral", "valuation_date": f"{year}-02-28", "valuer": "Independent Registered Valuers LLP"},
        {"particular": "Less: external liabilities", "book_value": round(-net_worth * .08, 2), "market_value": round(-net_worth * .08, 2), "ownership": "Consolidated", "encumbrance": "Existing obligations", "valuation_date": f"{year}-03-31", "valuer": "Audited accounts"},
        {"particular": "Adjusted tangible net worth", "book_value": net_worth, "market_value": round(net_worth * 1.18, 2), "ownership": "Consolidated", "encumbrance": "Net position", "valuation_date": f"{year}-03-31", "valuer": "Credit assessment"},
    ]

    projected_items = [
        ("Revenue from operations", revenue * 1.12, "Order-book conversion and market growth", "Downside assumes 8% lower volumes"),
        ("EBITDA", ebitda * 1.14, "Utilization and product-mix improvement", "Margin compressed by 150 bps"),
        ("Profit after tax", ebitda * .56, "Stable interest and effective tax rate", "Higher borrowing cost by 100 bps"),
        ("Operating cash flow", ebitda * .72, "Working-capital discipline", "Receivable days increase by 15"),
        ("Capital expenditure", requested * .62, "Approved CNC and automation program", "Capex delayed by six months"),
        ("Net worth", net_worth * 1.13, "Retention of forecast profits", "Dividend payout capped at 15%"),
        ("Total bank debt", requested * 1.70, "Existing plus proposed facilities", "No additional unapproved debt"),
        ("Debt / tangible net worth", .78, "Debt reduces after commissioning", "Peak downside leverage 1.05x"),
        ("Interest coverage ratio", 6.65, "EBITDA divided by finance cost", "Downside remains above 4.25x"),
        ("DSCR", 1.48, "Cash accrual supports amortization", "Downside minimum 1.20x"),
        ("Receivable days", 55, "Customer mix remains stable", "Downside 70 days"),
        ("Inventory days", 58, "Lean inventory program", "Downside 72 days"),
    ]
    projected = [
        {
            "particular": name,
            "forecast_year_1": round(value, 2),
            "forecast_year_2": round(value * (1.11 if value > 100 else 1.03), 2),
            "forecast_year_3": round(value * (1.22 if value > 100 else 1.06), 2),
            "assumption": assumption,
            "sensitivity": sensitivity,
        }
        for name, value, assumption, sensitivity in projected_items
    ]

    factors = (0.78, 0.89, 1.0)
    historical = []
    for statement_year, factor in zip((year - 2, year - 1, year), factors):
        sales = revenue * factor
        period_ebitda = ebitda * factor
        historical.append(
            {
                "statement_year": statement_year,
                "statement_date": f"{statement_year}-03-31",
                "statement_period_months": 12,
                "audit_method": "Audited",
                "external_auditor": "Synthetic & Co. Chartered Accountants",
                "currency_code": "INR",
                "unit_scale": "lakh",
                "sales_turnover": round(sales, 2),
                "sales_growth_pct": round(8.75 + (statement_year - year + 2) * 2.9, 2),
                "gross_margin_pct": round(31.2 + (statement_year - year + 2) * .75, 2),
                "net_operating_profit": round(period_ebitda * .82, 2),
                "net_profit_before_tax_sales_pct": round(period_ebitda * .68 / sales * 100, 2),
                "net_profit": round(period_ebitda * .51, 2),
                "ebitda": round(period_ebitda, 2),
                "net_cash_after_operations": round(period_ebitda * .62, 2),
                "net_worth": round(net_worth * factor, 2),
                "bank_borrowing": round(requested * (1.28 - factor * .3), 2),
                "total_liability": round(sales * .48, 2),
                "total_assets": round(sales * .92, 2),
                "debt_tangible_net_worth_pct": round(62 - (factor * 17.5), 2),
                "accounts_receivable_days": round(66 - factor * 10, 2),
                "accounts_payable_days": round(56 - factor * 8, 2),
                "inventory_days": round(72 - factor * 12, 2),
                "interest_coverage": round(4.9 + factor * 2.0, 2),
                "source_pdf_pages": f"{20 + statement_year - (year - 2)}-{22 + statement_year - (year - 2)}",
                "data_quality_note": "Reconciled to manufactured audited financial statements, GST returns and bank records.",
            }
        )

    forecasts = []
    for offset in (1, 2, 3):
        sales = revenue * (1.12**offset)
        forecast_ebitda = ebitda * (1.14**offset)
        forecasts.append(
            {
                "forecast_year": year + offset,
                "forecast_label": f"Base Case FY{year + offset}",
                "currency_code": "INR",
                "unit_scale": "lakh",
                "sales_turnover": round(sales, 2),
                "sales_growth_pct": round(12 - offset * .45, 2),
                "gross_margin_pct": round(33.0 + offset * .35, 2),
                "net_operating_profit": round(forecast_ebitda * .84, 2),
                "net_profit_before_tax_sales_pct": round(forecast_ebitda * .70 / sales * 100, 2),
                "net_profit": round(forecast_ebitda * .54, 2),
                "ebitda": round(forecast_ebitda, 2),
                "net_cash_after_operations": round(forecast_ebitda * .68, 2),
                "net_worth": round(net_worth * (1.13**offset), 2),
                "bank_borrowing": round(requested * (1.65 - offset * .18), 2),
                "total_liability": round(sales * (.46 - offset * .015), 2),
                "total_assets": round(sales * (.94 + offset * .01), 2),
                "debt_tangible_net_worth_pct": round(48 - offset * 5.2, 2),
                "accounts_receivable_days": 56 - offset,
                "accounts_payable_days": 49 - offset * .5,
                "inventory_days": 60 - offset,
                "interest_coverage": round(6.5 + offset * .55, 2),
                "model_name": "Bank Base Case Forecast Model",
                "model_note": "Forecast incorporates order book, capacity commissioning and working-capital assumptions.",
                "source_table": TABLE_NAMES[8],
            }
        )

    directors = list(context["directors"])
    ownership = [
        {"owner_details": f"{directors[0]} - Managing Director and promoter", "capital_amount": round(net_worth * .31, 2), "ownership_percent": 38.0, "owner_type": "Individual promoter", "board_rights": "Managing Director and nomination rights", "source_note": "Verified through MOA/AOA and KYC records.", "source_pdf_pages": "15-17"},
        {"owner_details": f"{directors[1]} Family Trust", "capital_amount": round(net_worth * .20, 2), "ownership_percent": 24.5, "owner_type": "Promoter trust", "board_rights": "One nominee director", "source_note": "Beneficial ownership declaration reviewed.", "source_pdf_pages": "16-18"},
        {"owner_details": f"{directors[2]} - Executive Director", "capital_amount": round(net_worth * .12, 2), "ownership_percent": 14.5, "owner_type": "Individual promoter", "board_rights": "Executive director", "source_note": "PAN and identity records verified.", "source_pdf_pages": "17-18"},
        {"owner_details": "Northbridge Industrial Growth Fund II", "capital_amount": round(net_worth * .14, 2), "ownership_percent": 17.0, "owner_type": "Institutional investor", "board_rights": "Observer and reserved-matter rights", "source_note": "Minority investor with no operating control.", "source_pdf_pages": "18-19"},
        {"owner_details": "Employee Stock Option Trust", "capital_amount": round(net_worth * .05, 2), "ownership_percent": 6.0, "owner_type": "Employee trust", "board_rights": "None", "source_note": "Vested and unvested employee option pool.", "source_pdf_pages": "19"},
    ]

    return {
        TABLE_NAMES[0]: balance_sheet,
        TABLE_NAMES[1]: cashflow,
        TABLE_NAMES[2]: income_statement,
        TABLE_NAMES[3]: bank_rows,
        TABLE_NAMES[4]: net_worth_rows,
        TABLE_NAMES[5]: projected,
        TABLE_NAMES[6]: [{
            "business_activities": f"{context['industry']} operations serving domestic and export customers across {context['geography']}.",
            "business_since": context["incorporation_year"],
            "relationship_status": "Existing banking relationship with working-capital, trade and term-loan exposure",
            "regulator_enquiry_date": f"{year - 1}-11-18",
            "regulator_enquiry_note": "No open material regulatory enquiry identified in the latest diligence review.",
            "current_rating": "A- / Stable",
            "current_rating_date": f"{year}-03-31",
            "current_rating_note": "Rating reflects stable cash flow, moderate leverage and established customer relationships.",
            "previous_rating": "BBB+ / Positive",
            "previous_rating_date": f"{year - 1}-03-31",
            "previous_rating_note": "Previous rating was constrained by working-capital intensity.",
            "bank_internal_rating": "Grade 4 - Acceptable Risk",
            "blacklisted": False,
            "blacklisted_note": "No blacklisting record found in internal or external screening.",
            "related_party_status": "Related parties identified and disclosed",
            "related_party_type": "Promoter-controlled supplier and property lessor",
            "politically_exposed_person": False,
            "pep_note": "No director or beneficial owner identified as a PEP.",
            "present_in_defaulter_list": False,
            "defaulter_list_note": "No match in the defaulter lists reviewed.",
            "source_pdf_pages": "Company Profile 8-14; KYC Credit Reports 2-6",
        }],
        TABLE_NAMES[7]: ownership,
        TABLE_NAMES[8]: historical,
        TABLE_NAMES[9]: forecasts,
        TABLE_NAMES[10]: [
            {"facility_type": "Working Capital Cash Credit", "facility_amount_existing": round(requested * .80, 2), "utilization": round(requested * .61, 2), "facility_amount_new": requested, "currency_code": "INR", "unit_scale": "lakh", "pricing": "1-year MCLR + 1.75%", "tenure": "12 months, annually renewable", "repayment": "On demand with monthly interest servicing", "purpose": "Inventory and receivable funding", "source_note": "Enhancement supports order-book growth."},
            {"facility_type": "Term Loan - CNC Expansion", "facility_amount_existing": round(requested * .45, 2), "utilization": round(requested * .37, 2), "facility_amount_new": round(requested * .60, 2), "currency_code": "INR", "unit_scale": "lakh", "pricing": "1-year MCLR + 2.00%", "tenure": "72 months including 6-month moratorium", "repayment": "Quarterly sculpted instalments", "purpose": "Machinery and automation capex", "source_note": "Disbursement against supplier invoices."},
            {"facility_type": "Letter of Credit Sublimit", "facility_amount_existing": round(requested * .22, 2), "utilization": round(requested * .11, 2), "facility_amount_new": round(requested * .28, 2), "currency_code": "INR", "unit_scale": "lakh", "pricing": "0.90% per annum plus SWIFT charges", "tenure": "Up to 180 days", "repayment": "At maturity from operating cash flow", "purpose": "Imported machinery and alloy inputs", "source_note": "Sublimit within working-capital exposure."},
            {"facility_type": "Bank Guarantee Sublimit", "facility_amount_existing": round(requested * .15, 2), "utilization": round(requested * .07, 2), "facility_amount_new": round(requested * .20, 2), "currency_code": "INR", "unit_scale": "lakh", "pricing": "1.00% per annum", "tenure": "Up to 24 months", "repayment": "Contingent; cash margin 10%", "purpose": "Performance and advance-payment guarantees", "source_note": "Beneficiaries are established OEM customers."},
        ],
        TABLE_NAMES[11]: [
            {"exposure_type": "Equipment finance", "lender": "Industrial Finance NBFC", "exposure_limit": round(requested * .30, 2), "exposure": round(requested * .22, 2), "security": "Specific charge on two forging presses", "currency_code": "INR", "unit_scale": "lakh", "repayment_status": "Regular", "source_note": "36 monthly instalments remaining."},
            {"exposure_type": "Supplier finance program", "lender": "Trade Finance Bank", "exposure_limit": round(requested * .20, 2), "exposure": round(requested * .11, 2), "security": "Assignment of confirmed payables", "currency_code": "INR", "unit_scale": "lakh", "repayment_status": "Regular", "source_note": "Program covers top steel suppliers."},
            {"exposure_type": "Vehicle loans", "lender": "Commercial Vehicle Finance Ltd", "exposure_limit": round(requested * .06, 2), "exposure": round(requested * .035, 2), "security": "Charge on financed vehicles", "currency_code": "INR", "unit_scale": "lakh", "repayment_status": "Regular", "source_note": "No overdue instalments."},
        ],
        TABLE_NAMES[12]: [
            {"collateral_category": "Land and building", "mitigant_type": "First-ranking mortgage", "description": "Primary manufacturing site and administrative building", "amount": round(net_worth * .43, 2), "currency_code": "INR", "unit_scale": "lakh", "valuation_date": f"{year}-03-15", "valuer": "Independent Registered Valuers LLP", "haircut_pct": 25, "eligible_value": round(net_worth * .43 * .75, 2), "source_note": "Title search and valuation reviewed."},
            {"collateral_category": "Plant and machinery", "mitigant_type": "Exclusive hypothecation", "description": "CNC machines, forging presses and finishing lines", "amount": round(net_worth * .48, 2), "currency_code": "INR", "unit_scale": "lakh", "valuation_date": f"{year}-03-15", "valuer": "Independent Registered Valuers LLP", "haircut_pct": 35, "eligible_value": round(net_worth * .48 * .65, 2), "source_note": "Asset register reconciled to invoices."},
            {"collateral_category": "Receivables", "mitigant_type": "Floating charge", "description": "Eligible receivables below 90 days", "amount": round(revenue * .18, 2), "currency_code": "INR", "unit_scale": "lakh", "valuation_date": f"{year}-03-31", "valuer": "Borrowing-base certificate", "haircut_pct": 25, "eligible_value": round(revenue * .18 * .75, 2), "source_note": "Excludes related-party and overdue debtors."},
            {"collateral_category": "Inventory", "mitigant_type": "Floating charge", "description": "Raw material, WIP and finished goods", "amount": round(revenue * .16, 2), "currency_code": "INR", "unit_scale": "lakh", "valuation_date": f"{year}-03-31", "valuer": "Stock audit", "haircut_pct": 35, "eligible_value": round(revenue * .16 * .65, 2), "source_note": "Subject to quarterly stock audit."},
            {"collateral_category": "Promoter support", "mitigant_type": "Personal guarantee", "description": "Joint and several guarantees from principal promoters", "amount": round(net_worth * .22, 2), "currency_code": "INR", "unit_scale": "lakh", "valuation_date": f"{year}-03-31", "valuer": "Net-worth declaration", "haircut_pct": 50, "eligible_value": round(net_worth * .11, 2), "source_note": "Guarantee documents to be executed before drawdown."},
        ],
        TABLE_NAMES[13]: [
            {"exception_code": "SEC-VAL-01", "end_date": f"{year}-09-30", "mitigant_exception_description": "Updated machinery valuation pending commissioning.", "exception_severity": "Medium", "status": "Open", "owner": "Relationship Manager", "action_plan": "Obtain final valuation and file charge modification.", "source_note": "Temporary exception approved until commissioning."},
            {"exception_code": "DOC-INS-02", "end_date": f"{year}-08-31", "mitigant_exception_description": "Renewed insurance endorsement naming the bank as loss payee is pending.", "exception_severity": "Low", "status": "Open", "owner": "Credit Administration", "action_plan": "Receive endorsement directly from insurer before first disbursement.", "source_note": "Broker confirmation is on file."},
            {"exception_code": "FIN-QTR-03", "end_date": f"{year}-07-31", "mitigant_exception_description": "Latest quarter provisional statements awaiting auditor review.", "exception_severity": "Low", "status": "Monitoring", "owner": "Borrower CFO", "action_plan": "Submit reviewed statements with covenant certificate.", "source_note": "Management accounts received and reconciled."},
        ],
        TABLE_NAMES[14]: [
            {"covenant_type": "Debt / tangible net worth", "reporting_date": f"{year}-03-31", "due_date": f"{year}-06-30", "description": "Maintain total debt within approved leverage ceiling.", "threshold_value": "<= 1.25x", "reported_value": "0.58x", "compliance_status": "Compliant", "testing_frequency": "Quarterly", "source_pdf_pages": "Financial statements 31-32", "source_note": "Calculated from adjusted tangible net worth."},
            {"covenant_type": "Interest coverage ratio", "reporting_date": f"{year}-03-31", "due_date": f"{year}-06-30", "description": "Maintain EBITDA to gross interest above minimum.", "threshold_value": ">= 4.00x", "reported_value": "6.20x", "compliance_status": "Compliant", "testing_frequency": "Quarterly", "source_pdf_pages": "Financial statements 31-32", "source_note": "Comfortable headroom under base case."},
            {"covenant_type": "DSCR", "reporting_date": f"{year}-03-31", "due_date": f"{year}-06-30", "description": "Maintain annual debt-service coverage.", "threshold_value": ">= 1.20x", "reported_value": "1.48x", "compliance_status": "Compliant", "testing_frequency": "Annual", "source_pdf_pages": "Projected financials 8-10", "source_note": "Downside case remains at threshold."},
            {"covenant_type": "Receivables over 120 days", "reporting_date": f"{year}-03-31", "due_date": f"{year}-04-30", "description": "Limit aged receivables as a share of gross debtors.", "threshold_value": "<= 10%", "reported_value": "4.8%", "compliance_status": "Compliant", "testing_frequency": "Monthly", "source_pdf_pages": "Receivables aging 3-5", "source_note": "Related-party balances excluded from drawing power."},
            {"covenant_type": "Dividend distribution", "reporting_date": f"{year}-03-31", "due_date": f"{year}-06-30", "description": "Dividend requires no default and leverage below 1.0x.", "threshold_value": "<= 20% of PAT", "reported_value": "12% of PAT", "compliance_status": "Compliant", "testing_frequency": "Annual", "source_pdf_pages": "Declarations 6", "source_note": "Board policy aligns distributions with debt reduction."},
        ],
        TABLE_NAMES[15]: [
            {"credit_committee_name": "Regional Corporate Credit Committee", "decision": "Approved with conditions", "resolution_by": "Committee Secretary", "meeting_date": f"{year}-05-18", "meeting_no": f"RCCC-{year}-0518-07", "resolution_summary": f"Approved renewal and enhancement for {company}, subject to security perfection and covenant reporting.", "conditions_precedent": "Execute facility documents; perfect mortgage and hypothecation; receive insurance endorsement; promoter contribution before capex drawdown.", "conditions_subsequent": "Quarterly covenant certificate; annual stock audit; updated machinery valuation within 90 days.", "final_approving_authority": "Head of Corporate Credit", "source_note": "Resolution based on the manufactured credit proposal."},
            {"credit_committee_name": "Documentation Review Committee", "decision": "Cleared for documentation", "resolution_by": "Credit Administration Head", "meeting_date": f"{year}-05-25", "meeting_no": f"DRC-{year}-0525-03", "resolution_summary": "Facility structure and security package cleared subject to listed exceptions.", "conditions_precedent": "Complete KYC refresh and legal title search.", "conditions_subsequent": "Close low-severity documentation exceptions by stated end dates.", "final_approving_authority": "Chief Credit Operations Officer", "source_note": "Follow-up to the main credit approval."},
        ],
    }
