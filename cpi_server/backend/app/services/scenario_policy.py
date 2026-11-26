"""What-if replay of published numeric checks for the synthetic CPI demo."""
from .semantic_matching import comparison, converted

# These clauses describe conditional duties or alternative authority bands.
CONDITIONS = {
    "Direct Manager Review and Approval for Facilities Below Threshold": "Direct manager approval",
    "Approval Authority for Compliant Exposures Between USD 50 Million and USD 200 Million": "Regional Credit Committee",
    "Approval Authority for Compliant Exposures Exceeding USD 200 Million": "Global Credit Committee",
    "CPC Escalation for Total Spreads Exceeding 500 bps": "Credit Policy Committee",
    "Enhanced Assessment for Exposures Exceeding Two Percent of Liquid Assets": "Enhanced liquidity assessment",
    "Early Warning Trigger for LCR Breach": "Notify ALCO and CRO",
    "Early Warning Trigger for Illiquid Asset Concentration": "Notify ALCO and CRO",
    "Approval Authority for Small Credit Exposures": "Business unit approval, subject to eligibility",
}

# Units for editable assumptions. Pricing and facility size come from the
# main simulator inputs, whose units are bps and currency millions.
ASSUMPTIONS = {
    "review_cycle_years": "years",
    "credit_exposure": "USD",
    "sample_review_percentage": "%",
    "single_credit_exposure_percentage": "%",
    "liquidity_coverage_ratio": "%",
    "illiquid_asset_concentration_percentage": "%",
    "credit_exposure_percentage": "%",
    "exception_duration_days": "days",
    "report_retention_years": "years",
}


def compare_breaches(review, inputs, assumptions=None):
    overrides = {key: (value, ASSUMPTIONS[key]) for key, value in (assumptions or {}).items()}
    overrides.update(total_spread=(inputs["pricing_bps"], "bps"),
                     facility_amount=(round(inputs["facility_amount"] * 1_000_000, 2), inputs["currency"]))
    rows = []
    for finding in review["findings"]:
        if finding["result"] != "Breach":
            continue
        checks = []
        for check in finding["metric_checks"]:
            metric = check["metric"]
            value = check["actual"]
            if metric in overrides:
                value = float(converted(*overrides[metric], check["unit"]))
            checks.append({
                "metric": metric, "baseline": check["actual"], "scenario": value, "unit": check["unit"],
                "operator": check["operator"], "threshold": check["threshold"],
                "condition_met": comparison(value, check["operator"], check["threshold"]),
            })
        meets = all(check["condition_met"] is True for check in checks)
        duty = CONDITIONS.get(finding["rule_name"])
        if duty:
            outcome = "Condition met · review required" if meets else "Condition not met"
        else:
            outcome = "Within limit" if meets else "Still outside limit"
        rows.append({
            "rule_id": finding["rule_id"], "rule_name": finding["rule_name"],
            "policy_name": finding["policy_name"], "source_clause": finding["source_clause"],
            "outcome": outcome, "duty": duty, "checks": checks,
        })
    return {"knowledge_fingerprint": review["knowledge_fingerprint"], "findings": rows}
