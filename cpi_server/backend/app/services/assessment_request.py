from fastapi import HTTPException
from .deal_retrieval import DealRetrievalAgent


def normalize_request_id(value):
    value = value.strip()
    if not value:
        raise ValueError("Select a credit request")
    return value.upper() if value.lower().startswith("cr-") else value


def deal_assessment_context(request_id, user):
    # Retrieve through the account-scoped service; never trust browser-supplied facts.
    result = DealRetrievalAgent().run(user)
    deal = next((d for d in result.get("deals", []) if d["id"] == request_id), None)
    if not deal:
        raise HTTPException(404, "The selected credit request is unavailable for this account")
    intake = deal.get("intake") or {}
    fields = ("rating", "exposure", "geography_risk", "concentration_limit_utilization",
              "adjusted_collateral", "post_approval_exposure", "approval_authority",
              "total_required_documents", "uploaded_required_documents", "customer_segment", "borrower_type",
              "collateral_type", "risk_category", "sector", "documents", "evidence")
    proposal = {key: deal.get(key) if deal.get(key) is not None else intake.get(key) for key in fields}
    proposal.update(credit_request_number=deal["id"], borrower_name=deal.get("customer"),
                    industry=deal.get("industry"), facility=deal.get("facility"),
                    requested_amount=deal.get("amount"), currency=deal.get("currency"),
                    geography=deal.get("geography"),
                    status={"Draft":"Pending", "In Progress":"In Review", "Changes Requested":"Escalated", "Exported":"Approved"}.get(deal.get("status"),deal.get("status")))
    # Preserve additional managed input fields without inventing display defaults.
    for key, value in intake.items():
        proposal.setdefault(key,value)
    for key,value in deal.items():
        if key not in ('intake','id','created_at','updated_at') and key not in proposal:
            proposal[key]=value
    if proposal.get('customer_segment') is None and deal.get('segment') is not None:
        proposal['customer_segment']=deal['segment']
    proposal["data_source"] = "Credit Dossier"
    return proposal
