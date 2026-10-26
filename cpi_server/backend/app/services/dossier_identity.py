"""Both applications use Credit Dossier as the shared identity authority."""
from datetime import datetime, timezone
from fastapi import HTTPException
from ..config import SHARED_DEAL_API_KEY
from ..database import db_connection
from ..security import public_user
from .shared_deals import call_shared_deals


def mirror_identity(identity, *, approved=True):
    with db_connection() as connection:
        existing = connection.execute("SELECT * FROM public.users WHERE LOWER(user_id)=LOWER(%s) FOR UPDATE", (identity['user_id'],)).fetchone()
        if existing and existing.get('auth_provider') != 'dossier':
            raise HTTPException(409, 'This username has a legacy CPI account. Complete the identity migration before signing in.')
        local_id = existing['user_id'] if existing else identity['user_id']
        row = connection.execute("""
            INSERT INTO public.users(user_id,password_hash,role,status,questions,created_at,
                approved_at,auth_provider,dossier_user_id,dossier_credential_version)
            VALUES (%s,'!dossier-managed!',%s,%s,'[]',%s,%s,'dossier',%s,%s)
            ON CONFLICT(user_id) DO UPDATE SET role=EXCLUDED.role,status=EXCLUDED.status,
                auth_provider='dossier',dossier_user_id=EXCLUDED.dossier_user_id,
                dossier_credential_version=EXCLUDED.dossier_credential_version,
                failed_attempts=0,locked=false
            RETURNING *
        """, (local_id,identity['role'],'approved' if approved else 'pending',
              datetime.now(timezone.utc),datetime.now(timezone.utc) if approved else None,
              identity['user_id'],identity.get('credential_version'))).fetchone()
    return public_user(row)


def authenticate_dossier_user(user_id,password):
    if not SHARED_DEAL_API_KEY:
        raise HTTPException(503, 'The shared account service is not configured.')
    identity = call_shared_deals({'user_id':user_id},{'user_id':user_id,'password':password},path='/identity/authenticate')
    if not identity.get('found'):
        return None
    if identity['role'] not in {'relationship_manager','credit_analyst'}:
        raise HTTPException(403,'This role cannot access CPI.')
    return mirror_identity(identity)


def identity_call(user_id,payload,action):
    return call_shared_deals({'user_id':user_id},payload,path='/identity/'+action)
