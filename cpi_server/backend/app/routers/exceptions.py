from fastapi import APIRouter, Depends, HTTPException
from ..schemas import CreateExceptionRequest, ExceptionAction
from ..security import current_user
from ..database import db_connection, shared_policy_connection, retry_on_db_conflict, run_db_transaction
from ..services.assessment_request import normalize_request_id, deal_assessment_context
from datetime import date
import json
from ..services.exception_rationale import generate_exception_rationale

router = APIRouter()

WORKFLOW_STEPS = ["Detected", "Reviewed", "Approved", "Remediated", "Closed"]


def _workflow_for_status(status: str) -> list[dict]:
    current_by_status = {
        "Active": "Reviewed",
        "Pending Approval": "Approved",
        "Remediation": "Remediated",
    }
    current = current_by_status.get(status)
    if status == "Closed":
        return [{"name": name, "status": "Done"} for name in WORKFLOW_STEPS]
    current_index = WORKFLOW_STEPS.index(current)
    return [
        {"name": name, "status": "Done" if index < current_index else "Current" if index == current_index else "Pending"}
        for index, name in enumerate(WORKFLOW_STEPS)
    ]

@router.get("/api/exceptions")
def exception_registry(status: str | None = None, _: dict = Depends(current_user)):
    factory = db_connection
    with factory() as connection:
        query = 'SELECT user_id AS account_user_id, exception_id AS id, COALESCE(source_request_id, credit_request_number) AS credit_request_number, exception_type AS type, clause_code AS clause, severity, exposure, owner, due_date AS due, status, description, rationale, workflow, history FROM "user".credit_request_exceptions'
        params = ()
        if status: query += " WHERE status = %s"; params = (status,)
        result = [dict(row) for row in connection.execute(query + " ORDER BY exception_id LIMIT 1000", params).fetchall()]
        for item in result:
            item["workflow"] = _workflow_for_status(item["status"])
        return result


@router.post("/api/exceptions", status_code=201)
def create_exception(payload: CreateExceptionRequest, user: dict = Depends(current_user)):
    if user.get('role') != 'relationship_manager':
        raise HTTPException(403, 'Only relationship managers can create exceptions.')
    if payload.status not in {'Active', 'Pending Approval'}:
        raise HTTPException(403, 'New exceptions must await credit analyst approval.')
    request_number = normalize_request_id(payload.credit_request_number)
    is_deal = request_number.startswith('deal_')
    deal_proposal = deal_assessment_context(request_number, user) if is_deal else None
    try:
        due_date = date.fromisoformat(payload.due_date)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Due date must be a valid date") from error
    if due_date < date.today():
        raise HTTPException(status_code=422, detail="Due date cannot be in the past")

    with db_connection() as connection:
        proposal = deal_proposal or connection.execute("""
            SELECT credit_request_number, borrower_name, industry, facility, rating,
                   exposure, requested_amount, status
            FROM credit_requests WHERE credit_request_number = %s
        """, (request_number,)).fetchone()
        if not proposal:
            raise HTTPException(status_code=404, detail="Credit request not found")
        stored_review = connection.execute("""
            SELECT review FROM ai_compliance_reviews
            WHERE COALESCE(source_request_id, credit_request_number) = %s
            ORDER BY created_at DESC, review_id DESC LIMIT 1
        """, (request_number,)).fetchone()

    exposure = int(proposal.get("exposure") or 0)
    severity = "Low" if exposure < 25_000_000 else "Medium" if exposure < 75_000_000 else "High"
    exception_context = {
        "type": payload.exception_type.strip(), "clause": payload.clause_code.strip().upper(),
        "description": payload.description.strip(), "exposure": exposure, "severity": severity,
        "due_date": due_date, "status": payload.status,
    }
    rationale = generate_exception_rationale(
        dict(proposal), exception_context, stored_review["review"] if stored_review else None,
        user["user_id"],
    )
    workflow = _workflow_for_status(payload.status)
    history = [{"date": str(date.today()), "event": "Exception created from Compliance Review", "actor": user["user_id"]}]
    def persist(connection):
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('credit_request_exceptions'))")
        next_number = connection.execute("""
            SELECT GREATEST(9000, COALESCE(MAX(NULLIF(regexp_replace(exception_id, '\\D', '', 'g'), '')::BIGINT), 9000)) + 1 AS value
            FROM credit_request_exceptions
        """).fetchone()["value"]
        exception_id = f"EX-{next_number}"
        row = connection.execute("""
            INSERT INTO credit_request_exceptions
                (exception_id, credit_request_number, source_request_id, exception_type, clause_code, severity,
                 exposure, owner, due_date, status, description, rationale, workflow, history)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
            RETURNING user_id AS account_user_id, exception_id AS id, COALESCE(source_request_id, credit_request_number) AS credit_request_number, exception_type AS type,
                      clause_code AS clause, severity, exposure, owner, due_date AS due,
                      status, description, rationale, workflow, history
        """, (exception_id, None if is_deal else request_number, request_number if is_deal else None, payload.exception_type.strip(), payload.clause_code.strip().upper(),
              severity, exposure, payload.owner.strip(), due_date, payload.status, payload.description.strip(),
              json.dumps(rationale), json.dumps(workflow), json.dumps(history))).fetchone()
        return row
    row = run_db_transaction(persist)
    return dict(row)

@router.delete("/api/exceptions/{exception_id}")
@retry_on_db_conflict
def delete_exception(exception_id: str, account_user_id: str | None = None, user: dict = Depends(current_user)):
    if user.get('role') not in {'relationship_manager', 'credit_analyst'}:
        raise HTTPException(403, 'Exception workflow access is unavailable.')
    account = account_user_id or user['user_id']
    if account != user['user_id'] and user['role'] != 'credit_analyst':
        raise HTTPException(403, 'You can only delete your own exceptions.')
    factory = shared_policy_connection if user['role'] == 'credit_analyst' else db_connection
    with factory() as connection:
        deleted = connection.execute(
            'DELETE FROM "user".credit_request_exceptions WHERE user_id=%s AND exception_id=%s RETURNING exception_id',
            (account, exception_id),
        ).fetchone()
        if not deleted:
            raise HTTPException(404, 'Exception not found')
    return {"exception_id": exception_id, "account_user_id": account, "deleted": True}


@router.post("/api/exceptions/{exception_id}/action")
@retry_on_db_conflict
def exception_action(exception_id: str, payload: ExceptionAction, _: dict = Depends(current_user)):
    if payload.action == 'approve' and _.get('role') != 'credit_analyst':
        raise HTTPException(403, 'Only credit analysts can approve exceptions.')
    if _.get('role') not in {'relationship_manager', 'credit_analyst'}:
        raise HTTPException(403, 'Exception workflow access is unavailable.')
    if payload.account_user_id and payload.account_user_id != _['user_id'] and _['role'] != 'credit_analyst':
        raise HTTPException(403, 'You can only update your own exceptions.')
    new_status = {
        "approve": "Remediation",
        "escalate": "Pending Approval",
        "remediate": "Closed",
        "close": "Closed",
    }[payload.action]
    workflow = _workflow_for_status(new_status)
    factory = shared_policy_connection if _['role'] == 'credit_analyst' else db_connection
    with factory() as connection:
        account = payload.account_user_id or _['user_id']
        item = connection.execute('SELECT status, history FROM "user".credit_request_exceptions WHERE user_id=%s AND exception_id=%s FOR UPDATE', (account, exception_id)).fetchone()
        if not item: raise HTTPException(status_code=404, detail="Exception not found")
        allowed = {
            "approve": {"Active", "Pending Approval"},
            "escalate": {"Active"},
            "remediate": {"Remediation"},
            "close": {"Remediation"},
        }
        if item["status"] not in allowed[payload.action]:
            raise HTTPException(status_code=409, detail=f"Cannot {payload.action} an exception in {item['status']} status")
        event = {'approve': 'Approved exception', 'escalate': 'Escalated exception', 'remediate': 'Remediated exception', 'close': 'Closed exception'}[payload.action]
        history = item["history"] + [{"date": str(date.today()), "event": event, "actor": _['user_id']}]
        connection.execute('UPDATE "user".credit_request_exceptions SET status=%s, workflow=%s::jsonb, history=%s::jsonb, updated_at=CURRENT_TIMESTAMP WHERE user_id=%s AND exception_id=%s', (new_status, json.dumps(workflow), json.dumps(history), account, exception_id))
        return {"exception_id": exception_id, "action": payload.action, "status": new_status, "actor": _['user_id']}
