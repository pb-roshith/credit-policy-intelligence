"""Authenticated server-to-server API; canonical deal records remain in Dossier."""
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.anomaly_alerts import UNKNOWN_IDENTITY_EVENT
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.deal import DealCreate
from app.schemas.input_validation import StrictInputModel
from pydantic import Field
from app.services.new_deal_agent import create_shared_deal, public_shared_deal
from app.services.library_sync_service import LibrarySyncService

router = APIRouter(prefix="/api/shared/deals", tags=["shared-deals"])


class CompanyDetailsRequest(StrictInputModel):
    name: str = Field(min_length=1, max_length=256)


class SharedCredentials(StrictInputModel):
    user_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def require_shared_key(x_shared_deal_key: str = Header(default="")):
    if not settings.SHARED_DEAL_API_KEY or not secrets.compare_digest(x_shared_deal_key, settings.SHARED_DEAL_API_KEY):
        raise HTTPException(401, "Shared service authentication failed.")


@router.post("/identity/authenticate", dependencies=[Depends(require_shared_key)])
def authenticate_identity(payload: SharedCredentials, request: Request, db: Session = Depends(get_db)):
    from app.auth import find_login_user, authenticate_user
    request.state.audit_user_id = payload.user_id
    if not find_login_user(db, payload.user_id, case_insensitive=True):
        request.state.audit_event_type = UNKNOWN_IDENTITY_EVENT
        return {"found": False}
    user = authenticate_user(db, payload.user_id, payload.password, request=request, case_insensitive=True)
    if user.role not in {"relationship_manager", "credit_analyst"}:
        raise HTTPException(403, "Use the CPI administrator login for administrator access.")
    request.state.audit_user_id = user.user_id
    return {"found": True, "user_id": user.user_id, "role": user.role, "credential_version": user.credential_version}


def shared_user(
    request: Request,
    x_shared_deal_key: str = Header(default=""),
    x_shared_user_id: str = Header(default=""),
    db: Session = Depends(get_db),
):
    if not settings.SHARED_DEAL_API_KEY or not secrets.compare_digest(x_shared_deal_key, settings.SHARED_DEAL_API_KEY):
        raise HTTPException(401, "Shared deal service authentication failed.")
    # Match the login ID, never the unrelated internal UUID or a browser-supplied owner.
    from sqlalchemy import func
    user = db.query(User).filter_by(user_id=x_shared_user_id).first()
    if not user:
        matches = db.query(User).filter(func.lower(User.user_id) == x_shared_user_id.strip().lower()).all()
        user = matches[0] if len(matches) == 1 else None
    if not user or not user.is_active or user.is_locked or not user.is_approved:
        raise HTTPException(403, "An active matching Credit Dossier account is required.")
    if user.role not in {"relationship_manager", "credit_analyst"}:
        raise HTTPException(403, "This account cannot access shared deals.")
    request.state.audit_user_id = user.user_id
    return user


@router.get("/identity")
def identity(user=Depends(shared_user)):
    return {"user_id": user.user_id, "role": user.role, "credential_version": user.credential_version}


@router.post("/retrieve")
def retrieve_deals(user=Depends(shared_user), db: Session = Depends(get_db)):
    from app.services.deal_retrieval_agent import retrieve_owned_deals
    return retrieve_owned_deals(db, user)


@router.get("/companies")
async def companies(user=Depends(shared_user)):
    from app.routers.mcp import list_companies
    return await list_companies(current_user=user)


@router.post("/companies/details")
async def company_details(payload: CompanyDetailsRequest, user=Depends(shared_user)):
    from app.routers.mcp import get_company_details
    return await get_company_details(company_name=payload.name, current_user=user)


@router.get("")
def list_shared_deals(user=Depends(shared_user), db: Session = Depends(get_db)):
    from app.services.deal_retrieval_agent import owned_records
    return owned_records(db, user)


@router.post("", status_code=201)
def create_deal(payload: DealCreate, tasks: BackgroundTasks, user=Depends(shared_user), db: Session = Depends(get_db)):
    if user.role != "relationship_manager":
        raise HTTPException(403, "Only relationship managers can create deals.")
    deal = create_shared_deal(db, payload, user)
    if deal.library_sync_status == "not_started":
        tasks.add_task(LibrarySyncService.sync_mcp_documents, deal.id)
    return public_shared_deal(deal)


# Both registration screens use one namespace and one password/recovery authority.
from app.routers.auth import (RegisterRequest as IdentityRegistration, UserIdRequest,
                              ResetPasswordRequest as IdentityReset)
from typing import Literal
from app.routers.auth import ConfigureSecurityQuestionsRequest


@router.post('/identity/security-questions')
def configure_identity_questions(
    payload: ConfigureSecurityQuestionsRequest, request: Request,
    user=Depends(shared_user), db: Session = Depends(get_db),
):
    from app.auth import authenticate_user
    from app.routers.auth import configure_security_questions
    verified = authenticate_user(db, user.user_id, payload.current_password, request=request, case_insensitive=True)
    return configure_security_questions(payload, verified, db)


@router.post('/identity/register', dependencies=[Depends(require_shared_key)], status_code=201)
def register_identity(payload: IdentityRegistration, request: Request, db: Session = Depends(get_db)):
    from app.routers.auth import register
    return register(payload, request, db)


@router.get('/identity/configuration', dependencies=[Depends(require_shared_key)])
def identity_configuration(db: Session = Depends(get_db)):
    from app.routers.auth import authentication_configuration
    return authentication_configuration(db)


@router.post('/identity/questions', dependencies=[Depends(require_shared_key)])
def identity_questions(payload: UserIdRequest, request: Request, db: Session = Depends(get_db)):
    from app.routers.auth import reset_password_questions
    return reset_password_questions(payload, request, db)


@router.post('/identity/reset-password', dependencies=[Depends(require_shared_key)])
def reset_identity_password(payload: IdentityReset, request: Request, db: Session = Depends(get_db)):
    from app.routers.auth import reset_password
    return reset_password(payload, request, db)


@router.post('/identity/approve', dependencies=[Depends(require_shared_key)])
def approve_identity(payload: UserIdRequest, request: Request, db: Session = Depends(get_db)):
    from app.auth import find_login_user
    user = find_login_user(db, payload.user_id, case_insensitive=True)
    if not user or user.role not in {'relationship_manager', 'credit_analyst'}:
        raise HTTPException(404, 'User account not found.')
    from datetime import datetime, timezone
    user.is_approved = True
    user.approved_at = datetime.now(timezone.utc)
    user.approved_by = 'cpi-admin'
    db.commit()
    return {'user_id': user.user_id, 'status': 'approved'}


@router.post('/identity/unlock', dependencies=[Depends(require_shared_key)])
def unlock_identity(payload: UserIdRequest, db: Session = Depends(get_db)):
    from app.auth import find_login_user
    user = find_login_user(db, payload.user_id, case_insensitive=True)
    if not user or user.role not in {'relationship_manager', 'credit_analyst'}:
        raise HTTPException(404, 'User account not found.')
    user.is_locked = False
    user.failed_login_attempts = 0
    user.locked_at = None
    db.commit()
    return {'message': 'Account unlocked.'}


class ImportedAnswer(StrictInputModel):
    question: str = Field(min_length=3, max_length=256)
    answer_hash: str = Field(pattern=r'^[a-f0-9]{32}:[a-f0-9]{64}$')


class ImportedIdentity(StrictInputModel):
    user_id: str = Field(min_length=3, max_length=64, pattern=r'^[A-Za-z0-9._-]+$')
    source_id: str = Field(min_length=3, max_length=64)
    password_hash: str = Field(pattern=r'^[a-f0-9]{32}:[a-f0-9]{64}$')
    role: Literal['relationship_manager', 'credit_analyst']
    approved: bool
    locked: bool
    security_answers: list[ImportedAnswer] = Field(min_length=3, max_length=3)
    replace_existing: bool = False


@router.post('/identity/import', dependencies=[Depends(require_shared_key)])
def import_identity(payload: ImportedIdentity, db: Session = Depends(get_db)):
    """One-time trusted migration: preserve hashes and linked business data."""
    import base64
    from sqlalchemy import func, text
    from app.models.user import SecurityAnswer, AuthSession
    from sqlalchemy.exc import IntegrityError
    source = 'cpi:' + payload.source_id
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {'name': 'identity:' + payload.user_id.lower()})
    user = db.query(User).filter(func.lower(User.user_id) == payload.user_id.lower()).with_for_update().first()
    if user and user.identity_source == source:
        return {'user_id': user.user_id, 'credential_version': user.credential_version, 'status': 'already_imported'}
    if user and (not payload.replace_existing or user.role == 'admin'):
        raise HTTPException(409, 'An independent Credit Dossier account already uses this user ID.')
    if len({answer.question.casefold() for answer in payload.security_answers}) != 3:
        raise HTTPException(422, 'Three distinct recovery questions are required.')
    def convert(encoded):
        salt, digest = encoded.split(':')
        return 'pbkdf2_sha256$310000$' + base64.urlsafe_b64encode(bytes.fromhex(salt)).decode() + '$' + base64.urlsafe_b64encode(bytes.fromhex(digest)).decode()
    if user is None:
        user = User(user_id=payload.user_id.lower(), password_hash=convert(payload.password_hash), role=payload.role)
        db.add(user)
    else:
        db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(synchronize_session=False)
        db.query(SecurityAnswer).filter(SecurityAnswer.user_id == user.id).delete(synchronize_session=False)
        user.credential_version += 1
    user.identity_source = source
    user.password_hash = convert(payload.password_hash)
    user.role = payload.role
    user.is_approved = payload.approved
    user.is_active = True
    user.is_locked = payload.locked
    user.failed_login_attempts = 0
    try:
        db.flush()
        for position, answer in enumerate(payload.security_answers, 1):
            db.add(SecurityAnswer(user_id=user.id, position=position, question=answer.question, answer_hash=convert(answer.answer_hash)))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'User ID or migration source already exists.') from exc
    return {'user_id': user.user_id, 'credential_version': user.credential_version, 'status': 'imported'}


from app.routers.admin import PasswordPolicyRequest as SharedPasswordPolicy


@router.post('/identity/password-policy', dependencies=[Depends(require_shared_key)])
def update_identity_password_policy(payload: SharedPasswordPolicy, request: Request, db: Session = Depends(get_db)):
    from app.routers.admin import update_password_policy
    return update_password_policy(payload, request, db)
