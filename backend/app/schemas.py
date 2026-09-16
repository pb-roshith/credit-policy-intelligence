from typing import Literal
from pydantic import BaseModel, Field, field_validator

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


class ScenarioRunRequest(BaseModel):
    scenario_name: str = Field(min_length=1, max_length=120)
    facility_amount: float = Field(ge=25, le=150, description="USD millions")
    collateral_coverage: float = Field(ge=50, le=130, description="Percent")
    risk_rating: Literal["BBB", "BB+", "BB-", "B+"]
    pricing_bps: int = Field(ge=100, le=600)
    tenor_years: int = Field(ge=1, le=12)
    covenants: Literal["Full", "Partial", "None"]

    @field_validator("scenario_name")
    @classmethod
    def clean_scenario_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Scenario name is required")
        return cleaned

class ExceptionAction(BaseModel):
    action: Literal["approve", "escalate", "remediate", "close"]
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


class GenerateExceptionsRequest(BaseModel):
    credit_request_numbers: list[str] = Field(min_length=1, max_length=1000)

    @field_validator("credit_request_numbers")
    @classmethod
    def clean_credit_request_numbers(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip().upper() for value in values if value.strip()))
        if not cleaned:
            raise ValueError("Select at least one credit request")
        return cleaned


class GenerateBorrowerExposureRequest(BaseModel):
    records_per_borrower: int = Field(ge=1, le=10)


class GeneratePolicyControlsRequest(BaseModel):
    controls_per_policy: int = Field(default=5, ge=1, le=5)


class PolicyCopilotRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=160)


class PortfolioChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class PortfolioChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    history: list[PortfolioChatMessage] = Field(default_factory=list, max_length=20)


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
    geography: Literal[
        "US Northeast", "US Southeast", "US Midwest", "US West", "Canada",
        "United Kingdom", "Europe", "Middle East & Africa", "Asia Pacific",
        "Latin America",
    ]
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

