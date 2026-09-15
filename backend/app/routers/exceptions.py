from fastapi import APIRouter, Depends, HTTPException
from ..schemas import CreateExceptionRequest, ExceptionAction
from ..security import current_user
from ..database import db_connection, initialize_user_store
from datetime import date, timedelta
import json
from ..services.exception_rationale import generate_exception_rationale

router = APIRouter()

@router.get("/api/exceptions")
def exception_registry(status: str | None = None, _: dict = Depends(current_user)):
    initialize_user_store()
    with db_connection() as connection:
        requests = connection.execute("SELECT credit_request_number, industry, exposure FROM credit_requests ORDER BY credit_request_number LIMIT 10").fetchall()
        types = [("Leverage", "CP-4.2"), ("Collateral", "COL-2.1"), ("Concentration", "RAF-3.5"), ("Covenant", "CP-6.4"), ("Delegation", "DEL-3.1")]
        for index, request in enumerate(requests, 1):
            kind, clause = types[index % len(types)]
            connection.execute("""INSERT INTO credit_request_exceptions
                (exception_id, credit_request_number, exception_type, clause_code, severity, exposure, owner, due_date, status, description, rationale, workflow, history)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb) ON CONFLICT (exception_id) DO NOTHING""", (
                f"EX-{8820 + index}", request["credit_request_number"], kind, clause, ["High", "Medium", "Low"][index % 3], request["exposure"],
                ["S. Chen", "M. Ruiz", "A. Patel", "J. Okafor"][index % 4], date.today() + timedelta(days=14 + index), ["Pending Approval", "Active", "Remediation"][index % 3],
                f"User-raised exception for {request['credit_request_number']} requiring policy review.",
                json.dumps({"why_detected": f"The {request['industry']} request was flagged against the applicable policy threshold.", "business_justification": "The business requires the facility to support near-term operating and investment needs.", "risk_implication": "Approval without controls may increase credit, concentration, and expected-loss exposure.", "recommended_remediation": "Obtain documented approval, add monitoring conditions, and review at the next covenant checkpoint.", "escalation_required": "Escalate if the exception remains open beyond the due date."}),
                json.dumps([{"name": "Detected", "status": "Done"}, {"name": "Reviewed", "status": "Done"}, {"name": "Approved", "status": "Current"}, {"name": "Remediated", "status": "Pending"}, {"name": "Closed", "status": "Pending"}]),
                json.dumps([{"date": str(date.today()), "event": "Detected by Compliance Review", "actor": "AI Compliance Agent"}])))
        query = "SELECT exception_id AS id, credit_request_number, exception_type AS type, clause_code AS clause, severity, exposure, owner, due_date AS due, status, description, rationale, workflow, history FROM credit_request_exceptions"
        params = ()
        if status: query += " WHERE status = %s"; params = (status,)
        return [dict(row) for row in connection.execute(query + " ORDER BY exception_id", params).fetchall()]


@router.post("/api/exceptions", status_code=201)
def create_exception(payload: CreateExceptionRequest, user: dict = Depends(current_user)):
    initialize_user_store()
    request_number = payload.credit_request_number.strip().upper()
    try:
        due_date = date.fromisoformat(payload.due_date)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Due date must be a valid date") from error
    if due_date < date.today():
        raise HTTPException(status_code=422, detail="Due date cannot be in the past")

    with db_connection() as connection:
        proposal = connection.execute("""
            SELECT credit_request_number, borrower_name, industry, facility, rating,
                   exposure, requested_amount, status
            FROM credit_requests WHERE credit_request_number = %s
        """, (request_number,)).fetchone()
        if not proposal:
            raise HTTPException(status_code=404, detail="Credit request not found")
        stored_review = connection.execute("""
            SELECT review FROM ai_compliance_reviews
            WHERE credit_request_number = %s
            ORDER BY created_at DESC, review_id DESC LIMIT 1
        """, (request_number,)).fetchone()

    exposure = int(proposal["exposure"])
    severity = "Low" if exposure < 25_000_000 else "Medium" if exposure < 75_000_000 else "High"
    exception_context = {
        "type": payload.exception_type.strip(), "clause": payload.clause_code.strip().upper(),
        "description": payload.description.strip(), "exposure": exposure, "severity": severity,
        "due_date": due_date, "status": payload.status,
    }
    rationale = generate_exception_rationale(dict(proposal), exception_context, stored_review["review"] if stored_review else None)
    workflow = [
        {"name": "Detected", "status": "Done"}, {"name": "Reviewed", "status": "Current"},
        {"name": "Approved", "status": "Pending"}, {"name": "Remediated", "status": "Pending"},
        {"name": "Closed", "status": "Pending"},
    ]
    history = [{"date": str(date.today()), "event": "Exception created from Compliance Review", "actor": user["user_id"]}]
    with db_connection() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('credit_request_exceptions'))")
        next_number = connection.execute("""
            SELECT GREATEST(9000, COALESCE(MAX(NULLIF(regexp_replace(exception_id, '\\D', '', 'g'), '')::BIGINT), 9000)) + 1 AS value
            FROM credit_request_exceptions
        """).fetchone()["value"]
        exception_id = f"EX-{next_number}"
        row = connection.execute("""
            INSERT INTO credit_request_exceptions
                (exception_id, credit_request_number, exception_type, clause_code, severity,
                 exposure, owner, due_date, status, description, rationale, workflow, history)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
            RETURNING exception_id AS id, credit_request_number, exception_type AS type,
                      clause_code AS clause, severity, exposure, owner, due_date AS due,
                      status, description, rationale, workflow, history
        """, (exception_id, request_number, payload.exception_type.strip(), payload.clause_code.strip().upper(),
              severity, exposure, payload.owner.strip(), due_date, payload.status, payload.description.strip(),
              json.dumps(rationale), json.dumps(workflow), json.dumps(history))).fetchone()
    return dict(row)

@router.post("/api/exceptions/{exception_id}/action")
def exception_action(exception_id: str, payload: ExceptionAction, _: dict = Depends(current_user)):
    initialize_user_store()
    new_status = {"approve": "Remediation", "escalate": "Pending Approval", "close": "Closed"}[payload.action]
    with db_connection() as connection:
        item = connection.execute("SELECT history FROM credit_request_exceptions WHERE exception_id=%s", (exception_id,)).fetchone()
        if not item: raise HTTPException(status_code=404, detail="Exception not found")
        history = item["history"] + [{"date": str(date.today()), "event": f"{payload.action.title()}d exception", "actor": payload.actor}]
        connection.execute("UPDATE credit_request_exceptions SET status=%s, history=%s::jsonb, updated_at=CURRENT_TIMESTAMP WHERE exception_id=%s", (new_status, json.dumps(history), exception_id))
        return {"exception_id": exception_id, "action": payload.action, "status": new_status, "actor": payload.actor}
