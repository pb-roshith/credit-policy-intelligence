"""Verify Dossier-only login and live CPI retrieval; roll back synthetic records."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi import FastAPI
from app.auth import hash_password
from app.config import settings
from app.database import SessionLocal, get_db
from app.models import User
from app.routers.shared_deals import router
from app.services.deal_service import DealService

CHILD = '''
import os
from contextlib import contextmanager
from http.cookies import SimpleCookie
from unittest.mock import patch
from fastapi import Request, Response, HTTPException
from app.database import db_connection
from app.schemas import LoginRequest
from app.routers.auth import login
from app.security import resolve_session
from app.services.deal_retrieval import DealRetrievalAgent
from app.routers.requests import create_shared_deal
connection = db_connection()
@contextmanager
def isolated_connection():
    yield connection
try:
    with patch('app.services.dossier_identity.db_connection', isolated_connection), \\
         patch('app.security.db_connection', isolated_connection), \\
         patch('app.routers.auth.db_connection', isolated_connection), \\
         patch('app.routers.auth.write_user_log'):
        user_id = os.environ['SMOKE_USER_ID']
        assert connection.execute('SELECT 1 FROM public.users WHERE user_id=%s', (user_id,)).fetchone() is None
        response = Response()
        request = Request({'type': 'http', 'method': 'POST', 'headers': [], 'client': ('127.0.0.1', 12345)})
        session = login(LoginRequest(user_id=user_id.upper(), password=os.environ['SMOKE_PASSWORD']), request, response)
        assert session['user']['dossier_user_id'] == user_id
        assert session['user']['auth_provider'] == 'dossier'
        stored = connection.execute('SELECT password_hash FROM public.users WHERE user_id=%s', (user_id,)).fetchone()
        assert stored['password_hash'] == '!dossier-managed!'
        cookies = SimpleCookie()
        for value in response.headers.getlist('set-cookie'):
            cookies.load(value)
        cookie_header = 'cpi_session=' + cookies['cpi_session'].value
        authenticated_request = Request({'type': 'http', 'method': 'GET', 'headers': [(b'cookie', cookie_header.encode())]})
        _, verified_session = resolve_session(authenticated_request)
        result = DealRetrievalAgent().run(verified_session['user'])
        assert result['status'] == 'agent', result['status']
        assert [deal['id'] for deal in result['deals']] == [os.environ['SMOKE_DEAL_ID']]
        try:
            create_shared_deal({}, verified_session['user'])
            raise AssertionError('CPI allowed deal creation')
        except HTTPException as error:
            assert error.status_code == 403
        print('Dossier-only credentials -> CPI identity link -> CPI session -> live retrieval agent -> exact owned deal; CPI creation blocked: PASS')
finally:
    connection.rollback()
    connection.close()
'''


def main():
    db = SessionLocal()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[get_db] = lambda: db
    server = uvicorn.Server(uvicorn.Config(api, log_level="error", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    repository = Path(__file__).resolve().parents[3] / "cpi_server"
    try:
        password = "Aa1!" + secrets.token_urlsafe(16)
        owner = User(user_id="identity_smoke_" + secrets.token_hex(8), password_hash=hash_password(password),
                     role="relationship_manager", is_active=True, is_approved=True)
        db.add(owner)
        db.flush()
        with patch.object(db, "commit", db.flush):
            deal = DealService.create_deal(db, {"customer": "Synthetic Dossier-only Borrower", "amount": 1000000, "currency": "INR"}, owner.id)
            thread.start()
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            assert server.started
            child_env = dict(os.environ)
            child_env.pop("DATABASE_URL", None)
            child_env.update(SHARED_DEAL_API_URL=f"http://127.0.0.1:{sock.getsockname()[1]}",
                             SHARED_DEAL_API_KEY=settings.SHARED_DEAL_API_KEY,
                             SMOKE_USER_ID=owner.user_id, SMOKE_PASSWORD=password, SMOKE_DEAL_ID=deal.id)
            executable = repository / ("backend/.venv/Scripts/python.exe" if os.name == "nt" else "backend/.venv/bin/python")
            result = subprocess.run([str(executable), "-c", CHILD], cwd=repository / "backend", env=child_env,
                                    capture_output=True, text=True, timeout=120)
            print(result.stdout.strip())
            if result.returncode:
                import re
                diagnostic = result.stderr
                for secret in (password, settings.SHARED_DEAL_API_KEY, settings.MISTRAL_API_KEY, settings.DATABASE_URL):
                    if secret:
                        diagnostic = diagnostic.replace(secret, "[redacted]")
                print(re.sub(r"postgres(?:ql)?[^\\s]+", "[database redacted]", diagnostic)[-3000:])
                raise RuntimeError("Dossier identity smoke failed.")
    finally:
        server.should_exit = True
        if thread.is_alive():
            thread.join(timeout=5)
        db.rollback()
        db.close()
        sock.close()
    print("Synthetic accounts, sessions and deal rolled back; existing accounts and passwords unchanged.")


if __name__ == "__main__":
    main()
