import json
from ..schemas import CreateCreditRequest

def public_credit_request(row: dict) -> dict:
    return {
        "credit_request_number": row["credit_request_number"],
        "borrower_id": row["borrower_id"],
        "borrower_name": row["borrower_name"],
        "industry": row["industry"],
        "geography": row["geography"],
        "exposure": row["exposure"],
        "facility": row["facility"],
        "rating": row["rating"],
        "requested_amount": row["requested_amount"],
        "status": row["status"],
        "compliance_score": row["compliance_score"],
        "collateral_coverage": float(row["collateral_coverage"]),
        "recommended_pricing_bps": row["recommended_pricing_bps"],
        "recommended_tenor_years": row["recommended_tenor_years"],
    }


RESULT_SCORES = {"PASS": 100, "WARNING": 50, "FAIL": 0}
PREFERRED_INDUSTRIES = {"manufacturing", "healthcare", "technology", "energy", "consumer"}
MONITORED_INDUSTRIES = {"transportation", "chemicals", "commercial re", "aviation"}
PASS_RATINGS = {"AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-"}
WARNING_RATINGS = {"BB+", "BB", "BB-"}


def compliance_status(score: float) -> str:
    if score >= 95:
        return "Fully Compliant"
    if score >= 75:
        return "Compliant with Exceptions"
    if score >= 50:
        return "Material Policy Deviations"
    return "Non-Compliant"


def calculate_compliance_score(connection, payload: CreateCreditRequest, post_approval_exposure: int) -> tuple[dict, str]:
    findings = []
    breached_rules = []
    recommendations = []

    policy_scores = [RESULT_SCORES[item.result] for item in payload.policy_clauses]
    policy_score = sum(policy_scores) / len(policy_scores)
    for clause in payload.policy_clauses:
        if clause.result != "PASS":
            finding = {
                "category": "Policy Rules Compliance",
                "check": clause.clause_code,
                "result": clause.result,
                "message": f"{clause.clause_name} returned {clause.result}",
            }
            findings.append(finding)
            if clause.result == "FAIL":
                breached_rules.append(finding)
            recommendations.append(f"Resolve {clause.clause_code}: {clause.clause_name}")

    rating = payload.rating.strip().upper()
    rating_result = "PASS" if rating in PASS_RATINGS else "WARNING" if rating in WARNING_RATINGS else "FAIL"
    industry = payload.industry.strip().casefold()
    industry_result = "PASS" if industry in PREFERRED_INDUSTRIES else "WARNING" if industry in MONITORED_INDUSTRIES else "FAIL"
    geography_result = {"Low": "PASS", "Medium": "WARNING", "High": "FAIL"}[payload.geography_risk]
    concentration = payload.concentration_limit_utilization
    concentration_result = "PASS" if concentration <= 80 else "WARNING" if concentration <= 100 else "FAIL"
    risk_checks = [
        ("Risk rating", rating_result, f"Risk rating is {rating}"),
        ("Industry appetite", industry_result, f"Industry is {payload.industry}"),
        ("Geography risk", geography_result, f"Geography risk is {payload.geography_risk}"),
        ("Concentration utilization", concentration_result, f"Concentration utilization is {concentration:.1f}%"),
    ]
    risk_score = sum(RESULT_SCORES[result] for _, result, _ in risk_checks) / len(risk_checks)
    for check, result, message in risk_checks:
        if result != "PASS":
            finding = {"category": "Risk Appetite Compliance", "check": check, "result": result, "message": message}
            findings.append(finding)
            if result == "FAIL":
                breached_rules.append(finding)
            recommendations.append(f"Review {check.lower()} before approval")

    coverage_ratio = payload.adjusted_collateral / post_approval_exposure
    collateral_score = 100 if coverage_ratio >= 1.20 else 75 if coverage_ratio >= 1.00 else 50 if coverage_ratio >= .80 else 0
    if collateral_score < 100:
        result = "FAIL" if collateral_score == 0 else "WARNING"
        finding = {
            "category": "Collateral Compliance",
            "check": "Collateral coverage",
            "result": result,
            "message": f"Adjusted collateral coverage is {coverage_ratio * 100:.1f}%",
        }
        findings.append(finding)
        if result == "FAIL":
            breached_rules.append(finding)
        recommendations.append("Obtain additional eligible collateral or reduce the requested amount")

    required_rule = connection.execute("""
        SELECT authority_name, authority_rank
        FROM approval_authority_rules
        WHERE maximum_post_approval_exposure IS NULL
           OR %s <= maximum_post_approval_exposure
        ORDER BY rule_order
        LIMIT 1
    """, (post_approval_exposure,)).fetchone()
    actual_rule = connection.execute("""
        SELECT authority_rank FROM approval_authority_rules
        WHERE LOWER(authority_name) = LOWER(%s)
    """, (payload.approval_authority,)).fetchone()
    actual_rank = actual_rule["authority_rank"] if actual_rule else 0
    required_rank = required_rule["authority_rank"]
    approval_score = 100 if actual_rank >= required_rank else 50 if actual_rank == required_rank - 1 else 0
    if approval_score < 100:
        result = "WARNING" if approval_score == 50 else "FAIL"
        finding = {
            "category": "Approval Authority Compliance",
            "check": "Approval authority",
            "result": result,
            "message": f"{required_rule['authority_name']} is required; {payload.approval_authority} was selected",
        }
        findings.append(finding)
        if result == "FAIL":
            breached_rules.append(finding)
        recommendations.append(f"Route the request to {required_rule['authority_name']}")

    document_score = min(100, payload.uploaded_required_documents / payload.total_required_documents * 100)
    if document_score < 100:
        result = "FAIL" if document_score < 50 else "WARNING"
        finding = {
            "category": "Documentation Completeness",
            "check": "Required documents",
            "result": result,
            "message": f"{payload.uploaded_required_documents} of {payload.total_required_documents} required documents are uploaded",
        }
        findings.append(finding)
        if result == "FAIL":
            breached_rules.append(finding)
        recommendations.append("Upload all missing required documents")

    category_scores = {
        "policyRulesCompliance": round(policy_score, 2),
        "riskAppetiteCompliance": round(risk_score, 2),
        "collateralCompliance": round(collateral_score, 2),
        "approvalAuthorityCompliance": round(approval_score, 2),
        "documentationCompleteness": round(document_score, 2),
    }
    overall_score = round(
        policy_score * .50 + risk_score * .20 + collateral_score * .15
        + approval_score * .10 + document_score * .05,
        2,
    )
    result = {
        "overallScore": overall_score,
        "complianceStatus": compliance_status(overall_score),
        "categoryScores": category_scores,
        "findings": findings,
        "breachedRules": breached_rules,
        "recommendations": list(dict.fromkeys(recommendations)),
    }
    return result, required_rule["authority_name"]


def persist_compliance_result(connection, credit_request_number: str, payload: CreateCreditRequest,
                              post_approval_exposure: int, result: dict, required_authority: str):
    with connection.cursor() as cursor:
        cursor.executemany("""
            INSERT INTO credit_request_policy_evaluations (
                credit_request_number, clause_code, clause_name, result
            ) VALUES (%s, %s, %s, %s)
        """, [
            (credit_request_number, clause.clause_code, clause.clause_name, clause.result)
            for clause in payload.policy_clauses
        ])
    connection.execute("""
        INSERT INTO credit_request_compliance (
            credit_request_number, geography_risk, concentration_limit_utilization,
            adjusted_collateral, post_approval_exposure, approval_authority,
            required_approval_authority, total_required_documents,
            uploaded_required_documents, overall_score, compliance_status,
            category_scores, findings, breached_rules, recommendations
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
        )
    """, (
        credit_request_number, payload.geography_risk,
        payload.concentration_limit_utilization, payload.adjusted_collateral,
        post_approval_exposure, payload.approval_authority, required_authority,
        payload.total_required_documents, payload.uploaded_required_documents,
        result["overallScore"], result["complianceStatus"],
        json.dumps(result["categoryScores"]), json.dumps(result["findings"]),
        json.dumps(result["breachedRules"]), json.dumps(result["recommendations"]),
    ))

