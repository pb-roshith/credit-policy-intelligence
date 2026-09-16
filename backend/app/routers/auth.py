from datetime import datetime, timezone
import hmac
import json
from fastapi import APIRouter, Depends, HTTPException, Header
from psycopg.errors import UniqueViolation
from ..config import ADMIN_PASSWORD, ADMIN_USER_ID, SECURITY_QUESTIONS, SESSIONS
from ..database import db_connection
from ..schemas import LoginRequest, PasswordPolicyRequest, RegisterRequest, ResetPasswordRequest
from ..security import create_session, current_admin, current_user, get_password_policy, hash_secret, normalize_answer, password_errors, public_user, verify_secret, write_admin_log

router = APIRouter()

@router.get("/api/auth/security-questions")
def get_security_questions():
    return {"questions": SECURITY_QUESTIONS}


@router.get("/api/auth/password-policy")
def public_password_policy():
    policy = get_password_policy()
    return {key: policy[key] for key in ("minimum_length", "maximum_length", "minimum_uppercase", "minimum_lowercase", "minimum_digits", "minimum_special")}


@router.get("/api/auth/me")
def authenticated_user(user: dict = Depends(current_user)):
    return {"user": user}


@router.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        session = SESSIONS.pop(authorization[7:], None)
        if session and session["user"]["role"] == "admin":
            write_admin_log(session["user"]["user_id"], "ADMIN_LOGOUT", session["user"]["user_id"], "Administrator signed out")
    return {"message": "Signed out"}


@router.post("/api/auth/register", status_code=201)
def register(payload: RegisterRequest):
    errors = password_errors(payload.password, payload.user_id)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    if len(payload.security_answers) != 3:
        raise HTTPException(status_code=422, detail="Exactly three security questions are required")
    questions = [entry.question.strip() for entry in payload.security_answers]
    if len({question.casefold() for question in questions}) != 3:
        raise HTTPException(status_code=422, detail="Security questions must be different")
    if payload.user_id.casefold() in {ADMIN_USER_ID.casefold(), '__legacy_unassigned__'}:
        raise HTTPException(status_code=409, detail="User ID is not available")
    stored_questions = [
        {"question": entry.question.strip(), "answer_hash": hash_secret(normalize_answer(entry.answer))}
        for entry in payload.security_answers
    ]
    try:
        with db_connection() as connection:
            connection.execute(
                "INSERT INTO public.users (user_id, password_hash, role, questions, created_at) VALUES (%s, %s, %s, %s, %s)",
                (payload.user_id.strip(), hash_secret(payload.password), payload.role, json.dumps(stored_questions), datetime.now(timezone.utc).isoformat()),
            )
    except UniqueViolation:
        raise HTTPException(status_code=409, detail="User ID already exists")
    return {"message": "Account created and awaiting administrator approval", "status": "pending"}


@router.post("/api/auth/login")
def login(payload: LoginRequest):
    if hmac.compare_digest(payload.user_id.casefold(), ADMIN_USER_ID.casefold()):
        if not hmac.compare_digest(payload.password, ADMIN_PASSWORD):
            raise HTTPException(status_code=401, detail="Invalid user ID or password")
        user = {"user_id": ADMIN_USER_ID, "role": "admin", "status": "active", "locked": False}
        session = create_session(user)
        write_admin_log(ADMIN_USER_ID, "ADMIN_LOGIN", ADMIN_USER_ID, "Administrator signed in")
        return session

    with db_connection() as connection:
        row = connection.execute("SELECT * FROM public.users WHERE LOWER(user_id) = LOWER(%s)", (payload.user_id.strip(),)).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid user ID or password")
        if row["status"] != "approved":
            raise HTTPException(status_code=403, detail="Your account is awaiting administrator approval")
        if row["locked"]:
            raise HTTPException(status_code=423, detail="Account locked. Reset your password or contact an administrator")
        if not verify_secret(payload.password, row["password_hash"]):
            attempts = row["failed_attempts"] + 1
            locked = attempts >= 3
            connection.execute("UPDATE public.users SET failed_attempts = %s, locked = %s WHERE user_id = %s", (attempts, locked, row["user_id"]))
            connection.commit()
            remaining = max(0, 3 - attempts)
            detail = "Account locked after three incorrect attempts" if locked else f"Invalid password. {remaining} attempt{'s' if remaining != 1 else ''} remaining"
            raise HTTPException(status_code=423 if locked else 401, detail=detail)
        connection.execute("UPDATE public.users SET failed_attempts = 0 WHERE user_id = %s", (row["user_id"],))
        user = public_user(row)
        return create_session(user)


@router.get("/api/auth/recovery/{user_id}")
def recovery_questions(user_id: str):
    with db_connection() as connection:
        row = connection.execute("SELECT questions FROM public.users WHERE LOWER(user_id) = LOWER(%s)", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User account not found")
    return {"questions": [item["question"] for item in json.loads(row["questions"])]}


@router.post("/api/auth/reset-password")
def reset_password(payload: ResetPasswordRequest):
    errors = password_errors(payload.password, payload.user_id)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    with db_connection() as connection:
        row = connection.execute("SELECT * FROM public.users WHERE LOWER(user_id) = LOWER(%s)", (payload.user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User account not found")
        stored = json.loads(row["questions"])
        submitted = {item.question.casefold(): normalize_answer(item.answer) for item in payload.security_answers}
        valid = len(submitted) == 3 and all(
            item["question"].casefold() in submitted and verify_secret(submitted[item["question"].casefold()], item["answer_hash"])
            for item in stored
        )
        if not valid:
            raise HTTPException(status_code=401, detail="One or more security answers are incorrect")
        connection.execute(
            "UPDATE public.users SET password_hash = %s, failed_attempts = 0, locked = FALSE WHERE user_id = %s",
            (hash_secret(payload.password), row["user_id"]),
        )
    return {"message": "Password reset successfully. Your account is unlocked"}


@router.get("/api/admin/users")
def admin_users(_: dict = Depends(current_admin)):
    with db_connection() as connection:
        rows = connection.execute("SELECT * FROM public.users ORDER BY created_at DESC").fetchall()
    return {"users": [public_user(row) for row in rows]}


@router.get("/api/admin/password-policy")
def admin_password_policy(_: dict = Depends(current_admin)):
    policy = get_password_policy()
    return {key: policy[key] for key in ("minimum_length", "maximum_length", "minimum_uppercase", "minimum_lowercase", "minimum_digits", "minimum_special", "updated_at", "updated_by")}


@router.put("/api/admin/password-policy")
def update_password_policy(payload: PasswordPolicyRequest, admin: dict = Depends(current_admin)):
    if payload.minimum_length > payload.maximum_length:
        raise HTTPException(status_code=422, detail="Minimum length cannot exceed maximum length")
    required_characters = payload.minimum_uppercase + payload.minimum_lowercase + payload.minimum_digits + payload.minimum_special
    if required_characters > payload.maximum_length:
        raise HTTPException(status_code=422, detail="Character requirements cannot exceed the maximum password length")
    with db_connection() as connection:
        connection.execute("""
            UPDATE public.password_policy SET
                minimum_length = %s, maximum_length = %s, minimum_uppercase = %s,
                minimum_lowercase = %s, minimum_digits = %s, minimum_special = %s,
                updated_at = %s, updated_by = %s
            WHERE id = 1
        """, (
            payload.minimum_length, payload.maximum_length, payload.minimum_uppercase,
            payload.minimum_lowercase, payload.minimum_digits, payload.minimum_special,
            datetime.now(timezone.utc), admin["user_id"],
        ))
    write_admin_log(admin["user_id"], "PASSWORD_POLICY_UPDATED", "Password policy", json.dumps(payload.model_dump()))
    return {"message": "Password policy updated", **payload.model_dump()}


@router.get("/api/admin/logs")
def administrative_logs(page: int = 1, admin: dict = Depends(current_admin)):
    page = max(1, page)
    page_size = 10
    offset = (page - 1) * page_size
    with db_connection() as connection:
        total = connection.execute("SELECT COUNT(*) AS count FROM public.administrative_logs").fetchone()["count"]
        rows = connection.execute(
            "SELECT id, actor, action, target, details, created_at FROM public.administrative_logs ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
            (page_size, offset),
        ).fetchall()
    return {"logs": rows, "page": page, "page_size": page_size, "total": total, "pages": max(1, (total + page_size - 1) // page_size)}


@router.post("/api/admin/users/{user_id}/approve")
def approve_user(user_id: str, admin: dict = Depends(current_admin)):
    with db_connection() as connection:
        cursor = connection.execute(
            "UPDATE public.users SET status = 'approved', approved_at = %s WHERE user_id = %s",
            (datetime.now(timezone.utc).isoformat(), user_id),
        )
    if not cursor.rowcount:
        raise HTTPException(status_code=404, detail="User account not found")
    write_admin_log(admin["user_id"], "USER_APPROVED", user_id, "User account approved")
    return {"message": f"{user_id} approved"}


@router.post("/api/admin/users/{user_id}/unlock")
def unlock_user(user_id: str, admin: dict = Depends(current_admin)):
    with db_connection() as connection:
        cursor = connection.execute("UPDATE public.users SET locked = FALSE, failed_attempts = 0 WHERE user_id = %s", (user_id,))
    if not cursor.rowcount:
        raise HTTPException(status_code=404, detail="User account not found")
    write_admin_log(admin["user_id"], "USER_UNLOCKED", user_id, "User account unlocked")
    return {"message": f"{user_id} unlocked"}
