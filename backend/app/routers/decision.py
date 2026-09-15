from fastapi import APIRouter, Depends
from ..schemas import DecisionRequest
from ..security import current_user

router = APIRouter()

@router.post("/api/decision")
def decision(request: DecisionRequest, _: dict = Depends(current_user)):
    ratio = request.requested_amount / request.annual_revenue
    checks = {"credit_score": request.credit_score >= 680, "facility_to_revenue": ratio <= .35, "collateral_coverage": request.collateral_coverage >= 100, "tenor": request.tenor_years <= 7}
    failed = [name for name, passed in checks.items() if not passed]
    score = max(0, min(100, round(100 - len(failed) * 12 - max(0, ratio - .25) * 80)))
    return {"decision": "APPROVE" if not failed else "REFER", "confidence": round(min(99.0, 70 + request.credit_score / 30), 1), "risk_appetite_score": score, "leverage_ratio": round(ratio, 3), "checks": checks, "reasons": [f"Failed policy check: {name.replace('_', ' ')}" for name in failed]}
