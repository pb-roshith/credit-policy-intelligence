from typing import Literal
from pydantic import BaseModel, Field

class SecurityAnswer(BaseModel):
    question: str = Field(min_length=3, max_length=200)
    answer: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    user_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=1, max_length=128)
    role: Literal["relationship_manager", "credit_analyst"]
    security_answers: list[SecurityAnswer]


class LoginRequest(BaseModel):
    user_id: str
    password: str


class ResetPasswordRequest(BaseModel):
    user_id: str
    password: str = Field(min_length=1, max_length=128)
    security_answers: list[SecurityAnswer]


class PasswordPolicyRequest(BaseModel):
    minimum_length: int = Field(ge=1, le=128)
    maximum_length: int = Field(ge=1, le=128)
    minimum_uppercase: int = Field(ge=0, le=128)
    minimum_lowercase: int = Field(ge=0, le=128)
    minimum_digits: int = Field(ge=0, le=128)
    minimum_special: int = Field(ge=0, le=128)

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


class CreateExceptionRequest(BaseModel):
    credit_request_number: str = Field(min_length=3, max_length=24)
    exception_type: str = Field(min_length=2, max_length=80)
    clause_code: str = Field(min_length=1, max_length=40)
    owner: str = Field(min_length=2, max_length=120)
    due_date: str
    status: Literal["Active", "Pending Approval", "Remediation", "Closed"] = "Active"
    description: str = Field(min_length=10, max_length=4000)


class GenerateCreditRequestsRequest(BaseModel):
    count: int = Field(ge=1, le=100)


class GenerateBorrowerExposureRequest(BaseModel):
    records_per_borrower: int = Field(ge=1, le=10)


class GeneratePolicyControlsRequest(BaseModel):
    controls_per_policy: int = Field(default=5, ge=1, le=5)


class PolicyCopilotRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=160)


class ComplianceReviewRequest(BaseModel):
    credit_request_number: str = Field(min_length=3, max_length=24)


class ComplianceCopilotRequest(ComplianceReviewRequest):
    question: str = Field(min_length=2, max_length=1000)


class PolicyClauseEvaluation(BaseModel):
    clause_code: str = Field(min_length=1, max_length=40)
    clause_name: str = Field(min_length=1, max_length=160)
    result: Literal["PASS", "WARNING", "FAIL"]


class CreateCreditRequest(BaseModel):
    borrower_id: int | None = Field(default=None, gt=0)
    borrower_name: str = Field(min_length=2, max_length=160)
    industry: str = Field(min_length=2, max_length=80)
    facility: str = Field(min_length=2, max_length=80)
    rating: str = Field(min_length=1, max_length=12)
    requested_amount: int = Field(gt=0)
    status: Literal["In Review", "Escalated", "Approved", "Pending", "Declined"]
    collateral_coverage: float = Field(default=100, ge=0, le=500)
    geography_risk: Literal["Low", "Medium", "High"] | None = None
    concentration_limit_utilization: float | None = Field(default=None, ge=0, le=1000)
    adjusted_collateral: int | None = Field(default=None, ge=0)
    approval_authority: str | None = Field(default=None, min_length=2, max_length=80)
    total_required_documents: int = Field(gt=0, le=1000)
    uploaded_required_documents: int = Field(ge=0, le=1000)
    policy_clauses: list[PolicyClauseEvaluation] = Field(default_factory=list, max_length=50)

