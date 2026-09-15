from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import BASE_DIR, MISTRAL_API_KEY, MISTRAL_POLICY_MODEL, POLICY_OUTPUT_DIR
from app.database import db_connection, ensure_database_exists, init_auth_db, init_credit_request_db
from app.routers import auth, compliance, controls, decision, exceptions, policies, requests
from app.manufacture_data import credit_requests, exposure_history, policy_controls, policy_pdfs

app = FastAPI(title="TCS Credit Policy Intelligence API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_database_exists()
init_auth_db()
init_credit_request_db()

for router in (
    auth.router,
    requests.router,
    compliance.router,
    credit_requests.router,
    exposure_history.router,
    policy_controls.router,
    policy_pdfs.router,
    controls.router,
    exceptions.router,
    policies.router,
    decision.router,
):
    app.include_router(router)
