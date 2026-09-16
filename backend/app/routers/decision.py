import json

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status

from ..database import db_connection
from ..schemas import DecisionRequest, ScenarioRunRequest
from ..security import current_user
from ..services.scenario_simulator import ScenarioRecommendationAgent, calculate_metrics, recommended_case

router = APIRouter()


def _scenario_response(row: dict, user_id: str) -> dict:
    return {
        "scenario_id": row["scenario_id"],
        "scenario_name": row["scenario_name"],
        "created_at": row["created_at"],
        "inputs": row["inputs"],
        "results": row["results"],
        "recommendations": row["recommendations"],
        "agent": "Mistral Credit Decision Scenario Recommendation Agent",
        "saved_by": user_id,
    }

@router.post("/api/decision")
def decision(request: DecisionRequest, _: dict = Depends(current_user)):
    ratio = request.requested_amount / request.annual_revenue
    checks = {"credit_score": request.credit_score >= 680, "facility_to_revenue": ratio <= .35, "collateral_coverage": request.collateral_coverage >= 100, "tenor": request.tenor_years <= 7}
    failed = [name for name, passed in checks.items() if not passed]
    score = max(0, min(100, round(100 - len(failed) * 12 - max(0, ratio - .25) * 80)))
    return {"decision": "APPROVE" if not failed else "REFER", "confidence": round(min(99.0, 70 + request.credit_score / 30), 1), "risk_appetite_score": score, "leverage_ratio": round(ratio, 3), "checks": checks, "reasons": [f"Failed policy check: {name.replace('_', ' ')}" for name in failed]}


@router.post("/api/decision-scenarios", status_code=status.HTTP_201_CREATED)
def run_scenario(request: ScenarioRunRequest, user: dict = Depends(current_user)):
    inputs = request.model_dump(exclude={"scenario_name"})
    with db_connection() as connection:
        duplicate = connection.execute(
            "SELECT 1 FROM decision_scenarios WHERE lower(btrim(scenario_name)) = lower(btrim(%s))",
            (request.scenario_name,),
        ).fetchone()
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="That scenario name already exists. Please choose another scenario name.",
        )

    results = calculate_metrics(inputs)
    improved_inputs, improved_results = recommended_case(inputs)
    agent_id, recommendations = ScenarioRecommendationAgent().run(
        inputs, results, improved_inputs, improved_results
    )
    stored_results = {
        **results,
        "recommended_case": {"inputs": improved_inputs, "results": improved_results},
    }
    try:
        with db_connection() as connection:
            saved = connection.execute('''INSERT INTO decision_scenarios
                (scenario_name, inputs, results, recommendations, agent_id)
                VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                RETURNING scenario_id, scenario_name, created_at''', (
                    request.scenario_name,
                    json.dumps(inputs),
                    json.dumps(stored_results),
                    json.dumps(recommendations),
                    agent_id,
                )).fetchone()
    except psycopg.errors.UniqueViolation as error:
        raise HTTPException(
            status_code=409,
            detail="That scenario name already exists. Please choose another scenario name.",
        ) from error
    return {
        **saved,
        "inputs": inputs,
        "results": stored_results,
        "recommendations": recommendations,
        "agent": "Mistral Credit Decision Scenario Recommendation Agent",
        "saved_by": user["user_id"],
    }


@router.get("/api/decision-scenarios")
def list_scenarios(_: dict = Depends(current_user)):
    with db_connection() as connection:
        return connection.execute('''SELECT scenario_id, scenario_name, created_at
            FROM decision_scenarios ORDER BY created_at DESC, scenario_id DESC''').fetchall()


@router.get("/api/decision-scenarios/{scenario_id}")
def get_scenario(scenario_id: int, user: dict = Depends(current_user)):
    with db_connection() as connection:
        row = connection.execute('''SELECT scenario_id, scenario_name, inputs, results,
                recommendations, created_at
            FROM decision_scenarios WHERE scenario_id = %s''', (scenario_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return _scenario_response(row, user["user_id"])
