"""CPI is a consumer of the common New Deal API, never another creator."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request

from fastapi import HTTPException
from ..config import SHARED_DEAL_API_URL, SHARED_DEAL_API_KEY, SHARED_DEAL_TIMEOUT_SECONDS, GEOGRAPHIES
from ..schemas import CreateCreditRequest, MAX_SAFE_MONETARY_AMOUNT


def call_shared_deals(user, payload=None, *, path=""):
    if not SHARED_DEAL_API_KEY:
        raise HTTPException(503, "The shared New Deal API is not configured.")
    request = Request(
        f"{SHARED_DEAL_API_URL}/api/shared/deals{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "X-Shared-Deal-Key": SHARED_DEAL_API_KEY,
                 "X-Shared-User-Id": user.get("dossier_user_id") or user["user_id"]},
        method="POST" if payload is not None else "GET",
    )
    try:
        # Do not forward service credentials to redirects.
        from urllib.request import build_opener, HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with build_opener(NoRedirect).open(request, timeout=SHARED_DEAL_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except HTTPError as error:
        status = error.code if error.code in {400, 401, 403, 404, 409, 422, 423, 429, 503} else 502
        detail = "The shared New Deal API could not complete this request."
        try:
            remote = json.load(error).get("detail")
            if isinstance(remote, (str, list)) and status in {400, 401, 403, 404, 409, 422, 423, 429, 503}:
                detail = remote
        except (ValueError, AttributeError):
            pass
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
