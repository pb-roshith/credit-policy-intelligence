from datetime import datetime, timezone
import hmac
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from ..config import ADMIN_PASSWORD, ADMIN_USER_ID, SECURITY_QUESTIONS, SESSION_COOKIE_SECURE
from ..database import db_connection
from ..schemas import AccountIdentifierRequest, LoginRequest, PasswordPolicyRequest, RegisterRequest, ResetPasswordRequest
from ..security import create_session, current_admin, current_user, get_password_policy, public_user, resolve_session, revoke_session, revoke_user_sessions, sensitive_admin, sensitive_user, write_admin_log, write_user_log

router = APIRouter()


from ..schemas import ConfigureRecoveryRequest


@router.post('/api/auth/profile/security-questions')
def configure_profile_recovery(payload: ConfigureRecoveryRequest, user: dict = Depends(sensitive_user)):
    from ..services.dossier_identity import identity_call
    return identity_call(user.get('dossier_user_id') or user['user_id'], {
        'current_password': payload.current_password,
        'security_questions': [entry.model_dump() for entry in payload.security_answers],
    }, 'security-questions')


def source_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def establish_session(response: Response, user: dict, application: str="cpi") -> dict:
    session = create_session(user,application)
    max_age = session["session_minutes"] * 60
    response.set_cookie(application+"_session", session.pop("token"), max_age=max_age,
                        httponly=True, secure=SESSION_COOKIE_SECURE,
                        samesite="strict", path="/")
    response.set_cookie(application+"_csrf", session.pop("csrf_token"), max_age=max_age,
                        httponly=False, secure=SESSION_COOKIE_SECURE,
                        samesite="strict", path="/")
    return session

@router.get("/api/auth/security-questions")
def get_security_questions():
    return {"questions": SECURITY_QUESTIONS}


@router.get("/api/auth/password-policy")
def public_password_policy():
    from ..services.shared_deals import call_shared_deals
    configuration = call_shared_deals({'user_id':'public-policy'}, path='/identity/configuration')
    policy = configuration['password_policy']
    return {target:policy[source] for target,source in (
        ('minimum_length','min_length'),('maximum_length','max_length'),
        ('minimum_uppercase','min_uppercase'),('minimum_lowercase','min_lowercase'),
        ('minimum_digits','min_digits'),('minimum_special','min_special'))}


@router.get("/api/auth/me")
def authenticated_user(request: Request, user: dict = Depends(current_user)):
    return {"user": user, "expires_at": request.state.session_expires_at}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token, _ = resolve_session(request)
    session = revoke_session(token)
    if session and session["role"] == "admin":
        write_admin_log(session["user_id"], "ADMIN_LOGOUT", session["user_id"], "Administrator signed out", source_ip(request))
    elif session:
        write_user_log(session["user_id"], "USER_LOGOUT", session["user_id"], "User signed out", source_ip(request))
    from ..security import session_application
    application=session_application(request)
    response.delete_cookie(application+"_session", path="/", samesite="strict")
    response.delete_cookie(application+"_csrf", path="/", samesite="strict")
    return {"message": "Signed out"}


@router.post("/api/auth/register", status_code=201)
def register(payload: RegisterRequest, request: Request):
    from ..services.dossier_identity import identity_call, mirror_identity
    name = payload.user_id.strip().lower()
    if name in {ADMIN_USER_ID.casefold(), '__legacy_unassigned__'}:
        raise HTTPException(409, 'User ID is not available')
    with db_connection() as connection:
        if connection.execute('SELECT 1 FROM public.users WHERE LOWER(user_id)=LOWER(%s)', (name,)).fetchone():
            raise HTTPException(409, 'User ID already exists')
    result = identity_call(name, {
        'user_id':name,'password':payload.password,'confirm_password':payload.password,
        'role':payload.role,'security_questions':[entry.model_dump() for entry in payload.security_answers],
    }, 'register')
    mirror_identity(result, approved=False)
    write_user_log(name, 'USER_REGISTERED', name, 'Shared account created; administrator approval pending', source_ip(request))
    return {'message':'Account created for both applications and awaiting administrator approval','status':'pending'}


@router.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, response: Response):
    if hmac.compare_digest(payload.user_id.casefold(), ADMIN_USER_ID.casefold()):
        if not ADMIN_PASSWORD or not hmac.compare_digest(payload.password.encode(), ADMIN_PASSWORD.encode()):
            write_admin_log(ADMIN_USER_ID, "ADMIN_LOGIN_FAILED", ADMIN_USER_ID,
                            "Invalid credentials", source_ip(request),
                            "error", "failure", "warning", "INVALID_CREDENTIALS")
            raise HTTPException(status_code=401, detail="Invalid user ID or password")
        user = {"user_id": ADMIN_USER_ID, "role": "admin", "status": "active", "locked": False}
        from ..security import session_application
        session = establish_session(response, user,session_application(request))
        write_admin_log(ADMIN_USER_ID, "ADMIN_LOGIN", ADMIN_USER_ID, "Administrator signed in", source_ip(request))
        return session

    from ..services.dossier_identity import authenticate_dossier_user
    dossier_user = authenticate_dossier_user(payload.user_id.strip(), payload.password)
    if dossier_user:
        from ..security import session_application
        session = establish_session(response, dossier_user,session_application(request))
        write_user_log(dossier_user["user_id"], "USER_LOGIN", dossier_user["user_id"], "Signed in using Credit Dossier identity", source_ip(request))
        return session

    write_user_log(payload.user_id.strip() or 'unknown', 'USER_LOGIN_FAILED', payload.user_id.strip() or None,
                   'Invalid shared account credentials', source_ip(request), 'error', 'failure', 'warning', 'INVALID_CREDENTIALS')
    raise HTTPException(401, 'Invalid user ID or password')


@router.post("/api/auth/recovery")
def recovery_questions(payload: AccountIdentifierRequest):
    from ..services.dossier_identity import identity_call
    user_id = payload.user_id.lower()
    return identity_call(user_id, {'user_id': user_id}, 'questions')


@router.post('/api/auth/reset-password')
def reset_password(payload: ResetPasswordRequest, request: Request):
    from ..services.dossier_identity import identity_call
    request.state.password_reset_user_id = payload.user_id
    result = identity_call(payload.user_id, {
        'user_id':payload.user_id.strip().lower(), 'new_password':payload.password,
        'confirm_password':payload.password,
        'security_questions':[entry.model_dump() for entry in payload.security_answers],
    }, 'reset-password')
    request.state.password_reset_completed = True
    try:
        with db_connection() as connection:
            connection.execute('UPDATE public.users SET failed_attempts=0,locked=false WHERE LOWER(user_id)=LOWER(%s)', (payload.user_id,))
        revoke_user_sessions(payload.user_id)
    finally:
        write_user_log(payload.user_id, 'PASSWORD_RESET', payload.user_id,
                       'Shared password reset succeeded', source_ip(request))
    return result


@router.get("/api/admin/users")
def admin_users(_: dict = Depends(current_admin)):
    with db_connection() as connection:
        rows = connection.execute("SELECT * FROM public.users ORDER BY created_at DESC").fetchall()
    return {"users": [public_user(row) for row in rows]}


@router.get("/api/admin/password-policy")
def admin_password_policy(_: dict = Depends(current_admin)):
    policy = get_password_policy()
    return {**{key:policy[key] for key in ("updated_at","updated_by")}, **public_password_policy()}


@router.put("/api/admin/password-policy")
def update_password_policy(payload: PasswordPolicyRequest, request: Request, admin: dict = Depends(sensitive_admin)):
    if payload.minimum_length > payload.maximum_length:
        raise HTTPException(status_code=422, detail="Minimum length cannot exceed maximum length")
    required_characters = payload.minimum_uppercase + payload.minimum_lowercase + payload.minimum_digits + payload.minimum_special
    if required_characters > payload.maximum_length:
        raise HTTPException(status_code=422, detail="Character requirements cannot exceed the maximum password length")
    from ..services.dossier_identity import identity_call
    requested_policy = {
        'min_length':payload.minimum_length,'max_length':payload.maximum_length,
        'min_uppercase':payload.minimum_uppercase,'min_lowercase':payload.minimum_lowercase,
        'min_digits':payload.minimum_digits,'min_special':payload.minimum_special,
    }
    confirmed_policy = identity_call(admin['user_id'], requested_policy, 'password-policy')
    if any(confirmed_policy.get(key) != value for key, value in requested_policy.items()):
        raise HTTPException(502, "The shared service did not confirm the requested password policy")
    with db_connection() as connection:
        saved = connection.execute("""
            UPDATE public.password_policy SET
                minimum_length = %s, maximum_length = %s, minimum_uppercase = %s,
                minimum_lowercase = %s, minimum_digits = %s, minimum_special = %s,
                updated_at = %s, updated_by = %s
            WHERE id = 1
            RETURNING id
        """, (
            payload.minimum_length, payload.maximum_length, payload.minimum_uppercase,
            payload.minimum_lowercase, payload.minimum_digits, payload.minimum_special,
            datetime.now(timezone.utc), admin["user_id"],
        )).fetchone()
        if saved is None:
            raise HTTPException(500, "Local password policy could not be updated")
    write_admin_log(admin["user_id"], "PASSWORD_POLICY_UPDATED", "Password policy", json.dumps(payload.model_dump()), source_ip(request))
    return {"message": "Password policy updated", **payload.model_dump()}


@router.get("/api/admin/logs")
def administrative_logs(page: int = 1, admin: dict = Depends(current_admin)):
    page = max(1, page)
    page_size = 10
    offset = (page - 1) * page_size
    with db_connection() as connection:
        total = connection.execute("SELECT COUNT(*) AS count FROM public.administrative_logs").fetchone()["count"]
        rows = connection.execute(
            "SELECT id AS event_id, actor AS action_owner_id, action, "
            "target AS resource_id, source_ip, event_type, outcome, severity, error_code, details, created_at "
            "FROM public.administrative_logs ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
            (page_size, offset),
        ).fetchall()
    return {"logs": rows, "page": page, "page_size": page_size, "total": total, "pages": max(1, (total + page_size - 1) // page_size)}


@router.get("/api/admin/user-logs")
def user_logs(page: int = 1, admin: dict = Depends(current_admin)):
    page = max(1, page)
    page_size = 10
    offset = (page - 1) * page_size
    with db_connection() as connection:
        total = connection.execute("SELECT COUNT(*) AS count FROM public.user_logs").fetchone()["count"]
        rows = connection.execute(
            "SELECT event_id, source_ip, action_owner_id, action, resource_id, "
            "event_type, outcome, severity, error_code, details, created_at "
            "FROM public.user_logs ORDER BY created_at DESC, event_id DESC LIMIT %s OFFSET %s",
            (page_size, offset),
        ).fetchall()
    return {"logs": rows, "page": page, "page_size": page_size, "total": total, "pages": max(1, (total + page_size - 1) // page_size)}


@router.post("/api/admin/users/approve")
def approve_user(payload: AccountIdentifierRequest, request: Request, admin: dict = Depends(sensitive_admin)):
    from ..services.dossier_identity import identity_call
    user_id = payload.user_id
    identity_call(admin['user_id'], {'user_id':user_id.strip().lower()}, 'approve')
    with db_connection() as connection:
        cursor = connection.execute(
            "UPDATE public.users SET status = 'approved', approved_at = %s WHERE user_id = %s",
            (datetime.now(timezone.utc).isoformat(), user_id),
        )
    if not cursor.rowcount:
        raise HTTPException(status_code=404, detail="User account not found")
    write_admin_log(admin["user_id"], "USER_APPROVED", user_id, "User account approved", source_ip(request))
    return {"message": f"{user_id} approved"}


@router.post("/api/admin/users/unlock")
def unlock_user(payload: AccountIdentifierRequest, request: Request, admin: dict = Depends(sensitive_admin)):
    from ..services.dossier_identity import identity_call
    user_id = payload.user_id
    identity_call(admin['user_id'], {'user_id':user_id.strip().lower()}, 'unlock')
    with db_connection() as connection:
        cursor = connection.execute("UPDATE public.users SET locked = FALSE, failed_attempts = 0 WHERE user_id = %s", (user_id,))
    if not cursor.rowcount:
        raise HTTPException(status_code=404, detail="User account not found")
    write_admin_log(admin["user_id"], "USER_UNLOCKED", user_id, "User account unlocked", source_ip(request))
    return {"message": f"{user_id} unlocked"}
