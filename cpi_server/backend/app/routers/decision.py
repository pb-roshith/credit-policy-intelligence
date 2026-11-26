import json

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..access_control import has_permission
from ..database import db_connection, run_db_transaction
from ..schemas import DecisionRequest, ScenarioRunRequest,ScenarioLinkRequest
from ..security import current_user
from ..services.scenario_simulator import ScenarioRecommendationAgent, calculate_metrics, recommended_case
from ..services.scenario_requests import request_baseline,available_requests
from ..services.scenario_policy import ASSUMPTIONS, compare_breaches

router = APIRouter()


def _risk_changes(results, baseline):
    metrics = calculate_metrics({**baseline['inputs'], 'currency': baseline['currency']}, include_sensitivity=False)
    return {key: round(results[key] - metrics[key], 6) for key in (
        'expected_loss', 'ecl_impact', 'rwa_impact', 'capital_impact',
        'concentration_impact', 'risk_appetite_score',
    )}


def _scenario_response(row: dict, user_id: str) -> dict:
    results = row["results"]
    snapshot = row.get("request_snapshot") or {}
    if results.get("policy_comparison") and "risk_changes" not in results:
        results = {**results, "risk_changes": _risk_changes(results, snapshot)}
    return {
        "scenario_id": row["scenario_id"],
        "scenario_name": row["scenario_name"],
        "credit_request_number": row.get('credit_request_number'),
        "request_snapshot": snapshot,
        "created_at": row["created_at"],
        "inputs": row["inputs"],
        "results": results,
        "recommendations": row["recommendations"],
        "agent": "Credit Decision Scenario Recommendation Agent",
        "saved_by": user_id,
    }

@router.post("/api/decision")
def decision(request: DecisionRequest, _: dict = Depends(current_user)):
    if not has_permission(_, "decision.execute"):
        raise HTTPException(403, "Decision execution is unavailable")
    ratio = request.requested_amount / request.annual_revenue
    checks = {"credit_score": request.credit_score >= 680, "facility_to_revenue": ratio <= .35, "collateral_coverage": request.collateral_coverage >= 100, "tenor": request.tenor_years <= 7}
    failed = [name for name, passed in checks.items() if not passed]
    score = max(0, min(100, round(100 - len(failed) * 12 - max(0, ratio - .25) * 80)))
    return {"decision": "APPROVE" if not failed else "REFER", "confidence": round(min(99.0, 70 + request.credit_score / 30), 1), "risk_appetite_score": score, "leverage_ratio": round(ratio, 3), "checks": checks, "reasons": [f"Failed policy check: {name.replace('_', ' ')}" for name in failed]}


@router.post("/api/decision-scenarios", status_code=status.HTTP_201_CREATED)
def run_scenario(request: ScenarioRunRequest, user: dict = Depends(current_user)):
    if not has_permission(user, "decision.execute"):
        raise HTTPException(403, "Decision execution is unavailable")
    baseline=request_baseline(request.credit_request_number,user)
    request_id=baseline['credit_request_number']
    if request.currency and request.currency!=baseline['currency']:
        raise HTTPException(409,'Request currency changed. Reset to the current request before running a scenario.')
    assumptions = request.policy_assumptions or {}
    if assumptions and (not baseline.get('policy_playpen') or
                        any(key not in ASSUMPTIONS or value < 0 or value > 1e15 for key, value in assumptions.items())):
        raise HTTPException(422, 'Use supported, non-negative policy assumptions for the demo request.')
    inputs = {**request.model_dump(exclude={"scenario_name","credit_request_number","currency","policy_assumptions"}),'currency':baseline['currency']}
    with db_connection() as connection:
        duplicate = connection.execute(
            "SELECT 1 FROM decision_scenarios WHERE credit_request_number=%s AND lower(btrim(scenario_name)) = lower(btrim(%s))",
            (request_id,request.scenario_name),
        ).fetchone()
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="That scenario name already exists for this credit request. Choose another name.",
        )

    results = calculate_metrics(inputs)
    improved_inputs, improved_results = recommended_case(inputs)
    if baseline.get('policy_playpen'):
        from ..services.compliance_agent import latest_stored_compliance_review
        review = latest_stored_compliance_review(request_id, user=user)
        if not review:
            raise HTTPException(409, 'Run a current Compliance Review before simulating policy checks.')
        try:
            results['policy_comparison'] = compare_breaches(review, inputs, assumptions)
        except (ValueError, ArithmeticError) as error:
            raise HTTPException(422, 'A scenario assumption is incompatible with the published metric unit.') from error
        results['policy_assumptions'] = assumptions
        results['risk_changes'] = _risk_changes(results, baseline)
        agent_id, recommendations = 'synthetic-policy-scenario', [
            'Compare the policy check values with the original assessment.',
            'Review any triggered approval or escalation requirements.',
            'Use the risk outputs to compare the proposed terms before deciding whether to change the request.',
        ]
    else:
        agent_id, recommendations = ScenarioRecommendationAgent().run(
            inputs, results, improved_inputs, improved_results, user["user_id"],request_context=baseline
        )
    stored_results = {
        **results,
        'scenario_changes':{field:{'baseline':baseline['inputs'].get(field),'scenario':value}
                            for field,value in inputs.items() if field!='currency' and value!=baseline['inputs'].get(field)},
        "recommended_case": {"inputs": improved_inputs, "results": improved_results},
    }
    try:
        def persist(connection):
            return connection.execute('''INSERT INTO decision_scenarios
                (scenario_name, credit_request_number, request_snapshot, inputs, results, recommendations, agent_id)
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                RETURNING scenario_id, scenario_name, created_at''', (
                    request.scenario_name,
                    request_id,
                    json.dumps(baseline),
                    json.dumps(inputs),
                    json.dumps(stored_results),
                    json.dumps(recommendations),
                    agent_id,
                )).fetchone()
        saved = run_db_transaction(persist)
    except psycopg.errors.UniqueViolation as error:
        raise HTTPException(
            status_code=409,
            detail="That scenario name already exists for this credit request. Choose another name.",
        ) from error
    return {
        **saved,
        'credit_request_number':request_id,'request_snapshot':baseline,
        "inputs": inputs,
        "results": stored_results,
        "recommendations": recommendations,
        "agent": "Credit Decision Scenario Recommendation Agent",
        "saved_by": user["user_id"],
    }


@router.get("/api/decision-scenarios")
def list_scenarios(credit_request_number:str=Query(min_length=1,max_length=160),user: dict = Depends(current_user)):
    request_id=request_baseline(credit_request_number,user)['credit_request_number']
    with db_connection() as connection:
        return connection.execute('''SELECT scenario_id, scenario_name, credit_request_number, created_at
            FROM decision_scenarios WHERE credit_request_number=%s
            ORDER BY created_at DESC, scenario_id DESC LIMIT 500''',(request_id,)).fetchall()


@router.get('/api/decision-scenarios/request-context')
def scenario_request_context(credit_request_number:str=Query(min_length=1,max_length=160),user:dict=Depends(current_user)):
    return request_baseline(credit_request_number,user)


@router.get('/api/decision-scenarios/requests')
def available_scenario_requests(user:dict=Depends(current_user)):
    return available_requests(user)


@router.get('/api/decision-scenarios/unlinked')
def unlinked_scenarios(credit_request_number:str|None=None,user:dict=Depends(current_user)):
    if credit_request_number:request_baseline(credit_request_number,user)
    with db_connection() as connection:
        return connection.execute('''SELECT scenario_id,scenario_name,created_at
            FROM decision_scenarios WHERE credit_request_number IS NULL
            ORDER BY created_at DESC,scenario_id DESC LIMIT 500''').fetchall()


@router.post('/api/decision-scenarios/{scenario_id}/link')
def link_scenario(scenario_id:int,body:ScenarioLinkRequest,user:dict=Depends(current_user)):
    baseline=request_baseline(body.credit_request_number,user)
    def persist(connection):
        row=connection.execute('''SELECT * FROM decision_scenarios
            WHERE scenario_id=%s AND credit_request_number IS NULL FOR UPDATE''',(scenario_id,)).fetchone()
        if not row:raise HTTPException(404,'Unlinked scenario not found')
        original_currency=row['inputs'].get('currency','USD')
        if original_currency!=baseline['currency']:
            raise HTTPException(409,'The earlier scenario uses another currency. Create a new request-based scenario instead.')
        snapshot={**baseline,'association_method':'USER_LINKED_LEGACY_SCENARIO','original_inputs_not_request_derived':True}
        return connection.execute('''UPDATE decision_scenarios SET credit_request_number=%s,request_snapshot=%s::jsonb
            WHERE scenario_id=%s RETURNING *''',(baseline['credit_request_number'],json.dumps(snapshot),scenario_id)).fetchone()
    try:row=run_db_transaction(persist)
    except psycopg.errors.UniqueViolation as error:
        raise HTTPException(409,'A scenario with that name already exists for this credit request.') from error
    return _scenario_response(row,user['user_id'])


@router.get("/api/decision-scenarios/{scenario_id}")
def get_scenario(scenario_id: int, credit_request_number:str=Query(min_length=1,max_length=160),user: dict = Depends(current_user)):
    request_id=request_baseline(credit_request_number,user)['credit_request_number']
    with db_connection() as connection:
        row = connection.execute('''SELECT scenario_id, scenario_name, inputs, results,
                recommendations, created_at, credit_request_number, request_snapshot
            FROM decision_scenarios WHERE scenario_id = %s AND credit_request_number=%s''', (scenario_id,request_id)).fetchone()
    if not row or row['credit_request_number']!=request_id:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return _scenario_response(row, user["user_id"])
