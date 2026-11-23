"""CPI is a consumer of the common New Deal API, never another creator."""
import json
import ssl
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request

from fastapi import HTTPException
from pydantic import Field, FiniteFloat, TypeAdapter, model_validator
from ..config import SHARED_DEAL_API_URL, SHARED_DEAL_API_KEY, SHARED_DEAL_TIMEOUT_SECONDS, GEOGRAPHIES
from ..schemas import CreateCreditRequest, MAX_SAFE_MONETARY_AMOUNT, StrictRequestModel, USER_ID_PATTERN


class SharedIdentity(StrictRequestModel):
    user_id: str = Field(min_length=1, max_length=64, pattern=USER_ID_PATTERN)
    role: str = Field(min_length=1, max_length=64)


class VersionedIdentity(SharedIdentity):
    credential_version: int = Field(ge=0)


class AuthenticatedIdentity(VersionedIdentity):
    found: Literal[True]


class UnknownIdentity(StrictRequestModel):
    found: Literal[False]


class SharedPasswordPolicy(StrictRequestModel):
    min_length: int = Field(ge=1, le=128)
    max_length: int = Field(ge=1, le=128)
    min_uppercase: int = Field(ge=0)
    min_lowercase: int = Field(ge=0)
    min_digits: int = Field(ge=0)
    min_special: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_requirements(self):
        required = self.min_uppercase + self.min_lowercase + self.min_digits + self.min_special
        if max(self.min_length, required) > self.max_length:
            raise ValueError("Password requirements exceed the maximum length")
        return self


class SharedConfiguration(StrictRequestModel):
    password_policy: SharedPasswordPolicy


class SharedQuestions(StrictRequestModel):
    questions: list[str]


class SharedMessage(StrictRequestModel):
    message: str


class SharedApproval(StrictRequestModel):
    user_id: str
    status: Literal["approved"]


class SharedImport(StrictRequestModel):
    user_id: str
    credential_version: int
    status: Literal["imported", "already_imported"]


class SharedDeal(StrictRequestModel):
    id: str
    customer: str
    industry: str
    geography: str
    facility: str
    currency: str
    amount: FiniteFloat
    status: str
    intake: dict | None = None


class SharedDealRetrieval(StrictRequestModel):
    deals: list[SharedDeal]
    status: Literal["agent", "direct"]
    source: str


RESPONSE_SCHEMAS = {
    "": TypeAdapter(list[SharedDeal]),
    "/retrieve": TypeAdapter(SharedDealRetrieval),
    "/identity": TypeAdapter(VersionedIdentity),
    "/identity/authenticate": TypeAdapter(AuthenticatedIdentity | UnknownIdentity),
    "/identity/register": TypeAdapter(SharedIdentity),
    "/identity/configuration": TypeAdapter(SharedConfiguration),
    "/identity/questions": TypeAdapter(SharedQuestions),
    "/identity/reset-password": TypeAdapter(SharedMessage),
    "/identity/security-questions": TypeAdapter(SharedMessage),
    "/identity/approve": TypeAdapter(SharedApproval),
    "/identity/unlock": TypeAdapter(SharedMessage),
    "/identity/import": TypeAdapter(SharedImport),
    "/identity/password-policy": TypeAdapter(SharedPasswordPolicy),
}
CREATED_DEAL_SCHEMA = TypeAdapter(SharedDeal)
SHARED_TLS_CONTEXT = ssl.create_default_context()
SHARED_TLS_CONTEXT.minimum_version = ssl.TLSVersion.TLSv1_2
ACCOUNT_RESPONSE_PATHS = {
    "/identity/authenticate", "/identity/register", "/identity/approve", "/identity/import",
}
SHARED_CLIENT_ERRORS = {
    400: "Check the information you entered and try again.",
    401: "Authentication failed. Check your credentials or sign in again.",
    403: "This action was denied. Check your account permissions or contact your administrator.",
    404: "The requested item could not be found. Check your selection and try again.",
    409: "This action conflicts with the current account settings. Refresh and try again.",
    422: "Check that the information you entered meets the displayed requirements.",
    423: "Your account is locked. Contact your administrator.",
    429: "Too many attempts. Wait and try again.",
    503: "The service is temporarily unavailable. Please try again later.",
}


def call_shared_deals(user, payload=None, *, path=""):
    if not SHARED_DEAL_API_KEY:
        raise HTTPException(503, "The shared New Deal API is not configured.")
    caller_id = user.get("dossier_user_id") or user["user_id"]
    request = Request(
        f"{SHARED_DEAL_API_URL}/api/shared/deals{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "X-Shared-Deal-Key": SHARED_DEAL_API_KEY,
                 "X-Shared-User-Id": caller_id},
        method="POST" if payload is not None else "GET",
    )
    try:
        # Do not forward service credentials to redirects.
        from urllib.request import build_opener, HTTPRedirectHandler, HTTPSHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with build_opener(NoRedirect, HTTPSHandler(context=SHARED_TLS_CONTEXT)).open(
            request, timeout=SHARED_DEAL_TIMEOUT_SECONDS
        ) as response:
            try:
                result = json.load(response)
                schema = CREATED_DEAL_SCHEMA if not path and payload is not None else RESPONSE_SCHEMAS[path]
                schema.validate_python(result, strict=True)
                if path == "/identity" or (path in ACCOUNT_RESPONSE_PATHS and result.get("found") is not False):
                    expected_id = caller_id if path == "/identity" else payload["user_id"]
                    if result["user_id"].casefold() != expected_id.strip().casefold():
                        raise ValueError("Shared response account does not match the request")
                if path == "/identity/register" and result["role"] != payload["role"]:
                    raise ValueError("Shared response role does not match the registration")
            except (ValueError, KeyError) as error:
                raise HTTPException(502, "Invalid response from the shared service.") from error
            return result
    except HTTPError as error:
        status = error.code if error.code in SHARED_CLIENT_ERRORS else 502
        detail = SHARED_CLIENT_ERRORS.get(status, "The service could not complete the request. Please try again later.")
        error.close()
        raise HTTPException(status, detail) from error
    except (URLError, TimeoutError, ValueError) as error:
        raise HTTPException(503, "The shared New Deal API is unavailable. Retry with the same request ID.") from error


def compliance_payload(deal):
    """Only project deals compatible with CPI's existing USD policy model."""
    intake = deal.get("intake") or {}
    amount = deal["amount"]
    status = {"Draft": "Pending", "In Progress": "In Review", "Changes Requested": "Escalated",
              "Exported": "Approved"}.get(deal["status"], deal["status"])
    if (deal["currency"] != "USD" or deal["geography"] not in GEOGRAPHIES
            or amount <= 0 or amount > MAX_SAFE_MONETARY_AMOUNT or int(amount) != amount
            or len(deal["customer"]) > 160 or len(deal["industry"]) > 80
            or len(deal["customer"].strip()) < 2 or len(deal["industry"].strip()) < 2
            or status not in {"Pending", "In Review", "Escalated", "Approved", "Declined"}):
        return None
    return CreateCreditRequest(
        borrower_name=deal["customer"], industry=deal["industry"], geography=deal["geography"],
        facility=deal["facility"], rating=intake.get("rating", "BB"), requested_amount=int(amount),
        status=status,
        collateral_coverage=float(intake.get("collateral_coverage", 100)),
        total_required_documents=intake.get("total_required_documents", 1),
        uploaded_required_documents=intake.get("uploaded_required_documents", 0),
    )
