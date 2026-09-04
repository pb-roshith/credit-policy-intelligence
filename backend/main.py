from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="TCS Credit Policy Intelligence API", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

REQUESTS = [
    {"id": "CR-10241", "borrower": "Meridian Steel Holdings", "industry": "Manufacturing", "requested_amount": 45_000_000, "rating": "BB", "status": "In Review", "compliance_score": 78},
    {"id": "CR-10242", "borrower": "Harbor Point Realty", "industry": "Commercial RE", "requested_amount": 85_000_000, "rating": "BB-", "status": "Escalated", "compliance_score": 62},
    {"id": "CR-10243", "borrower": "Northwind Logistics", "industry": "Transportation", "requested_amount": 25_000_000, "rating": "BBB", "status": "Approved", "compliance_score": 94},
]
EXCEPTIONS = [
    {"id": "EX-8821", "type": "Leverage", "clause": "CP-4.2", "severity": "High", "exposure": 85_000_000, "owner": "S. Chen", "due": "2026-08-05", "status": "Pending Approval"},
    {"id": "EX-8822", "type": "Collateral", "clause": "COL-2.1", "severity": "High", "exposure": 62_000_000, "owner": "M. Ruiz", "due": "2026-07-28", "status": "Active"},
    {"id": "EX-8823", "type": "Concentration", "clause": "RAF-3.5", "severity": "Medium", "exposure": 140_000_000, "owner": "A. Patel", "due": "2026-08-12", "status": "Remediation"},
]
POLICIES = [
    {"id": "CP-Wholesale-v4.2", "title": "Wholesale Credit Policy", "version": "4.2", "effective": "2026-01-15", "status": "Active"},
    {"id": "COL-2.1", "title": "Collateral Coverage Standard", "version": "2.1", "effective": "2026-03-01", "status": "Active"},
    {"id": "RAF-3.5", "title": "Risk Appetite Framework", "version": "3.5", "effective": "2026-04-01", "status": "Active"},
]

class DecisionRequest(BaseModel):
    annual_revenue: float = Field(default=250_000_000, gt=0)
    requested_amount: float = Field(gt=0)
    credit_score: int = Field(default=680, ge=300, le=900)
    sector: str = "Manufacturing"
    collateral_coverage: float = Field(default=100, ge=0, le=200)
    tenor_years: int = Field(default=5, ge=1, le=30)

class ExceptionAction(BaseModel):
    action: Literal["approve", "escalate", "close"]
    actor: str = "Sarah Chen"

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "credit-policy-intelligence", "date": date.today()}

@app.get("/api/summary")
def summary():
    return {"exposure": 4_820_000_000, "ecl_provision": 312_600_000, "policy_compliance": 92, "open_exceptions": 148, "active_requests": 1245}

@app.get("/api/requests")
def credit_requests(status: str | None = None):
    return [item for item in REQUESTS if status is None or item["status"].lower() == status.lower()]

@app.get("/api/exceptions")
def exception_registry(status: str | None = None):
    return [item for item in EXCEPTIONS if status is None or item["status"].lower() == status.lower()]

@app.post("/api/exceptions/{exception_id}/action")
def exception_action(exception_id: str, payload: ExceptionAction):
    item = next((row for row in EXCEPTIONS if row["id"] == exception_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Exception not found")
    item["status"] = {"approve": "Remediation", "escalate": "Pending Approval", "close": "Closed"}[payload.action]
    return {"exception": item, "action": payload.action, "actor": payload.actor}

@app.get("/api/policies")
def policies():
    return POLICIES

@app.post("/api/decision")
def decision(request: DecisionRequest):
    ratio = request.requested_amount / request.annual_revenue
    checks = {"credit_score": request.credit_score >= 680, "facility_to_revenue": ratio <= .35, "collateral_coverage": request.collateral_coverage >= 100, "tenor": request.tenor_years <= 7}
    failed = [name for name, passed in checks.items() if not passed]
    score = max(0, min(100, round(100 - len(failed) * 12 - max(0, ratio - .25) * 80)))
    return {"decision": "APPROVE" if not failed else "REFER", "confidence": round(min(99.0, 70 + request.credit_score / 30), 1), "risk_appetite_score": score, "leverage_ratio": round(ratio, 3), "checks": checks, "reasons": [f"Failed policy check: {name.replace('_', ' ')}" for name in failed]}
