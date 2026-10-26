"""Live cross-app verification. All synthetic database writes are rolled back.

Run from the Dossier backend: python scripts/smoke_shared_deal.py --user LOGIN_ID
The login must be an approved business user in Credit Dossier.
The retrieval conversation contains only deal IDs and a count.
"""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi import FastAPI
from app.config import settings
from app.database import SessionLocal, get_db
from app.routers.shared_deals import router

CHILD = """
import os
from app.services.shared_deals import call_shared_deals
from app.services.deal_retrieval import DealRetrievalAgent
user = {'user_id': os.environ['SMOKE_LOGIN_ID']}
canonical = call_shared_deals(user)
result = DealRetrievalAgent().run(user)
assert {deal['id'] for deal in result['deals']} == {deal['id'] for deal in canonical}
assert result['status'] == 'agent', result['status']
print('Live read-only retrieval: all', len(result['deals']), 'owned Dossier deals returned with exact canonical IDs; no copies created.')
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True)
    args = parser.parse_args()
    api = FastAPI()
    api.include_router(router)
    db = SessionLocal()
    api.dependency_overrides[get_db] = lambda: db
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(api, log_level="error", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    repository = Path(__file__).resolve().parents[3] / "cpi_server"
    try:
        with patch.object(db, "commit", db.flush), patch("app.routers.shared_deals.LibrarySyncService.sync_mcp_documents"):
            thread.start()
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.05)
            assert server.started, "Temporary shared API failed to start."
            child_env = dict(os.environ)
            # Each application must load its own database and identity settings.
            child_env.pop("DATABASE_URL", None)
            child_env.update(SHARED_DEAL_API_URL=f"http://127.0.0.1:{port}",
                             SHARED_DEAL_API_KEY=settings.SHARED_DEAL_API_KEY, SMOKE_LOGIN_ID=args.user)
            executable = repository / "backend/.venv/Scripts/python.exe"
            if os.name != "nt":
                executable = repository / "backend/.venv/bin/python"
            result = subprocess.run([str(executable), "-c", CHILD], cwd=repository / "backend",
                                    env=child_env, capture_output=True, text=True, timeout=120)
            print(result.stdout.strip())
            if result.returncode:
                import re
                diagnostic = result.stderr
                for secret in (settings.SHARED_DEAL_API_KEY, settings.MISTRAL_API_KEY, settings.DATABASE_URL):
                    if secret:
                        diagnostic = diagnostic.replace(secret, "[redacted]")
                diagnostic = re.sub(r"postgres(?:ql)?[^\s\"']+", "[database connection redacted]", diagnostic)
                print(diagnostic[-4000:])
                raise RuntimeError("Cross-app smoke failed; check accounts and service configuration.")
    finally:
        server.should_exit = True
        if thread.is_alive():
            thread.join(timeout=5)
        db.rollback()
        db.close()
        sock.close()
    print("Read-only check completed; temporary HTTP server stopped.")


if __name__ == "__main__":
    main()
