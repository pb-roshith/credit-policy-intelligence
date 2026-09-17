from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import initialize_database
from app.routers import auth, compliance, controls, dashboard, decision, exceptions, policies, requests
from app.manufacture_data import credit_requests, exposure_history, policy_controls, policy_pdfs

initialize_database()

app = FastAPI(title="TCS Credit Policy Intelligence API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router,
    requests.router,
    dashboard.router,
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
