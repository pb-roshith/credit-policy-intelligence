"""Install a repeatable, synthetic cross-tab demo in an existing CPI account."""
import argparse
from hashlib import sha256
from datetime import date, timedelta
from pathlib import Path
import sys

from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import APP_ENV
from app.database import account_user_id, resolve_borrower, run_db_transaction, shared_policy_connection
from app.risk_knowledge.semantic_extraction import digest
from app.routers.decision import run_scenario, list_scenarios
from app.schemas import ScenarioRunRequest
from app.services.scenario_policy import CONDITIONS
from app.services.scenario_requests import request_baseline
from app.routers.exceptions import _workflow_for_status
from app.services.current_knowledge import current_review
from app.services.rule_assessment import assessment_request_context
from app.services.semantic_assessment import build_assessment, persist_assessment
from app.services.semantic_matching import load_matcher
from app.services.semantic_rag import explain_assessment

REQUEST = "CR-90001"
BORROWER = "Harborline Aviation (Demo)"
EXCEPTION = "EX-DEMO-HARBORLINE"
EXPOSURE = 40_000_000
STATUS = "Pending Approval"


def install_request(db, today):
    borrower_id = resolve_borrower(db, BORROWER)
    db.execute("""
        INSERT INTO credit_requests (credit_request_number, borrower_id, borrower_name,
            industry, geography, exposure, facility, rating, requested_amount, status,
            compliance_score, collateral_coverage, recommended_tenor_years, recommended_pricing_bps)
        VALUES (%s,%s,%s,'Aviation','US Northeast',%s,'Aircraft Finance','BBB',
            20000000,'In Review',0,80,5,80)
    """, (REQUEST, borrower_id, BORROWER, EXPOSURE))
    facts = {
        "total_spread": 80,
        "currency_spread_adjustment": 40,
        "credit_exposure": EXPOSURE,
        "facility_amount": 20_000_000,
        "fact_units": {
            "total_spread": "bps", "currency_spread_adjustment": "bps",
            "credit_exposure": "USD", "facility_amount": "USD",
        },
    }
    db.execute("""
        INSERT INTO credit_request_compliance (credit_request_number, geography_risk,
            concentration_limit_utilization, adjusted_collateral, post_approval_exposure,
            approval_authority, required_approval_authority, total_required_documents,
            uploaded_required_documents, overall_score, compliance_status, category_scores,
            findings, breached_rules, recommendations, synthetic_assessment_data)
        VALUES (%s,'Low',60,48000000,60000000,'Credit Committee','Credit Committee',
            5,0,0,'Not assessed','{}','[]','[]','[]',%s)
    """, (REQUEST, Jsonb(facts)))
    db.execute("""
        INSERT INTO borrower_exposure_history (borrower_id, facility_reference, facility_type,
            reporting_month, original_exposure, scheduled_payment, actual_payment,
            outstanding_exposure, payment_status)
        VALUES (%s,%s,'Aircraft Finance',%s,%s,0,0,%s,'Current')
    """, (borrower_id, REQUEST, today.replace(day=1), EXPOSURE, EXPOSURE))


def install_demo(db, owner, matcher, today):
    db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"cpi-demo:{owner}",))
    existing = db.execute("SELECT borrower_name FROM credit_requests WHERE credit_request_number=%s", (REQUEST,)).fetchone()
    if not existing:
        install_request(db, today)
    elif existing["borrower_name"] != BORROWER:
        raise ValueError(f"{REQUEST} is already used by a different borrower.")

    db.execute("""
        UPDATE credit_requests SET recommended_pricing_bps=80 WHERE credit_request_number=%s
          AND recommended_pricing_bps=325
    """, (REQUEST,))
    db.execute("""
        UPDATE credit_request_compliance
        SET synthetic_assessment_data=synthetic_assessment_data || '{"scenario_policy_playpen":true}'
        WHERE credit_request_number=%s AND NOT synthetic_assessment_data @> '{"scenario_policy_playpen":true}'
    """, (REQUEST,))
    request_id, proposal = assessment_request_context(REQUEST, connection=db)
    stored = db.execute("""
        SELECT review_id,review FROM ai_compliance_reviews WHERE source_request_id=%s
        ORDER BY created_at DESC,review_id DESC LIMIT 1
    """, (REQUEST,)).fetchone()
    if (stored and current_review(stored["review"], matcher.fingerprint)
            and stored["review"]["applicability_report"]["request_fingerprint"] == digest(proposal)):
        review = stored["review"]
        review_id = stored["review_id"]
    else:
        review = build_assessment(request_id, proposal, matcher, evaluation_date=today, manufacture_missing=True)
        review["graph_rag_explanation"] = explain_assessment(review, use_ai=False)
        review_id = persist_assessment(db, request_id, review, owner)

    spread = [f for f in review["findings"] if f["rule_name"] == "Total Spread Minimum Boundary"
              and f["result"] == "Breach" and f["observed_value"] == 80]
    if len(spread) != 1 or not review["counts"]["PASS"] or proposal["exposure"] != EXPOSURE:
        raise ValueError("The current graph or request facts no longer reproduce the demo pass and spread breach.")
    breaches = [finding for finding in review["findings"] if finding["result"] == "Breach"]
    for finding in breaches:
        suffix = sha256(finding["rule_id"].encode()).hexdigest()[:5].translate(str.maketrans("0123456789", "ghijklmnop"))
        exception_id = EXCEPTION if finding is spread[0] else f"{EXCEPTION}-{suffix}"
        install_exception(db, owner, matcher, today, finding, exception_id)
    return review_id, review["outcome_counts"]


def install_exception(db, owner, matcher, today, finding, exception_id):
    knowledge = {
        "knowledge_fingerprint": matcher.fingerprint,
        "semantic_rule_id": finding["rule_id"],
        "policy_id": finding["policy_id"],
    }
    saved = db.execute("""
        SELECT status, credit_request_number, rationale FROM credit_request_exceptions WHERE exception_id=%s
    """, (exception_id,)).fetchone()
    if saved:
        if saved["credit_request_number"] != REQUEST or saved["rationale"].get("knowledge_context") != knowledge:
            raise ValueError(f"{exception_id} already exists with different rule evidence.")
        return

    description = f"{finding['policy_name']}, clause {finding['source_clause']}. {finding['actual']} against {finding['expected_condition']}."
    duty = CONDITIONS.get(finding["rule_name"])
    rationale = {
        "generation_status": "demo",
        "knowledge_context": knowledge,
        "why_detected": description,
        "business_justification": "Synthetic demo case for reviewing the recorded assessment finding.",
        "risk_implication": (
            f"This source clause defines a conditional duty: {duty}. Review the condition and scope."
            if duty else "The measured value is outside the threshold recorded in the assessment."
        ),
        "recommended_remediation": (
            "Confirm whether the source condition applies and document the applicable approval or escalation."
            if duty else "Compare the saved simulator cases and verify the proposed control or term change."
        ),
        "escalation_required": "The credit analyst must review this recorded finding before closure.",
    }
    db.execute("""
        INSERT INTO credit_request_exceptions (exception_id, credit_request_number, exception_type,
            clause_code, severity, exposure, owner, due_date, status, description, rationale, workflow, history)
        VALUES (%s,%s,%s,%s,'Medium',%s,%s,%s,%s,%s,%s,%s,%s)
    """, (exception_id, REQUEST, finding["rule_name"][:80], str(finding["source_clause"])[:40], EXPOSURE, owner,
          today + timedelta(days=30), STATUS, description, Jsonb(rationale), Jsonb(_workflow_for_status(STATUS)),
          Jsonb([{"date": str(today), "event": "Demo exception raised from Compliance Review", "actor": owner}])))


# One row per what-if, plus a baseline and a combined package. Values for
# conditional clauses illustrate when a duty becomes relevant.
SCENARIOS = [
    ("01 Original request", {}, {}),
    ("02 Reprice to 100 bps", {"pricing_bps": 100}, {}),
    ("03 Reprice to 180 bps", {"pricing_bps": 180}, {}),
    ("04 Resize to USD 12M", {"facility_amount": 12}, {}),
    ("05 Resize below USD 1M - manager review", {"facility_amount": 0.9}, {}),
    ("06 Collateral review at two years", {}, {"review_cycle_years": 2}),
    ("07 USD 80M exposure - regional approval", {}, {"credit_exposure": 80_000_000}),
    ("08 USD 210M exposure - global approval", {}, {"credit_exposure": 210_000_000}),
    ("09 Price at 520 bps - CPC escalation", {"pricing_bps": 520}, {}),
    ("10 Sample 12 percent of exposures", {}, {"sample_review_percentage": 12}),
    ("11 Exposure above 2 percent - enhanced assessment", {}, {"single_credit_exposure_percentage": 2.2}),
    ("12 Liquidity stress - LCR at 105 percent", {}, {"liquidity_coverage_ratio": 105}),
    ("13 Liquidity stress - illiquid concentration at 16 percent", {}, {"illiquid_asset_concentration_percentage": 16}),
    ("14 Exposure below 1 percent - business unit approval", {}, {"credit_exposure_percentage": 0.8}),
    ("15 Limit exception to 60 days", {}, {"exception_duration_days": 60}),
    ("16 Retain reports for seven years", {}, {"report_retention_years": 7}),
    ("17 Combined remediation package", {
        "pricing_bps": 180, "facility_amount": 12, "collateral_coverage": 110,
        "tenor_years": 4, "covenants": "Full",
    }, {
        "review_cycle_years": 2, "sample_review_percentage": 12,
        "exception_duration_days": 60, "report_retention_years": 7,
    }),
]


def install_scenarios(owner):
    actor = {"user_id": owner, "role": "relationship_manager"}
    baseline = request_baseline(REQUEST, actor)
    existing = {row["scenario_name"] for row in list_scenarios(REQUEST, actor)}
    for name, changes, assumptions in SCENARIOS:
        if name in existing:
            continue
        request = ScenarioRunRequest(
            credit_request_number=REQUEST, currency=baseline["currency"], scenario_name=name,
            policy_assumptions=assumptions, **{**baseline["inputs"], **changes},
        )
        run_scenario(request, actor)
    return len(SCENARIOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True, help="Existing relationship manager account ID")
    args = parser.parse_args()
    if APP_ENV != "development":
        parser.error("Use a development CPI database.")
    with shared_policy_connection() as db:
        owner = db.execute("""
            SELECT user_id FROM public.users WHERE user_id=%s AND role='relationship_manager'
                AND status='approved' AND NOT locked
        """, (args.account,)).fetchone()
    if not owner:
        parser.error("Choose an approved, unlocked relationship manager account.")
    matcher = load_matcher()
    scope = account_user_id.set(args.account)
    try:
        review_id, outcomes = run_db_transaction(
            lambda db: install_demo(db, args.account, matcher, date.today()))
        scenarios = install_scenarios(args.account)
    finally:
        account_user_id.reset(scope)
    print(f"{REQUEST} | {BORROWER} | {args.account} | review {review_id} | {outcomes['Breach']} linked exceptions | {scenarios} scenarios")
    print(outcomes)


if __name__ == "__main__":
    main()
