"""Dashboard request totals use authorized records, without display assumptions."""
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

STATUS_MAP = {"Draft": "Pending", "In Progress": "In Review",
              "Changes Requested": "Escalated", "Exported": "Approved"}


def request_totals(deals, local, reviews):
    from .current_knowledge import current_review
    reviews=[r for r in reviews if current_review(r.get('review') or {})]
    latest = {(row.get("account_user_id"), row["request_id"]): row["review"] for row in reviews}
    shared_latest = {row["request_id"]: row["review"] for row in sorted(reviews, key=lambda r: str(r.get("created_at") or "")) if not row["request_id"].startswith('CR-')}
    by_deal = {row["shared_deal_id"]: row for row in local if row.get("shared_deal_id")}
    records = []
    for deal in deals:
        linked = by_deal.get(deal["id"], {})
        review = shared_latest.get(deal["id"]) or latest.get((linked.get("account_user_id"), linked.get("credit_request_number"))) or {}
        records.append({"status": STATUS_MAP.get(deal["status"], deal["status"]),
                        "currency": deal.get("currency"), "amount": deal.get("amount"),
                        "score": review.get("overall_score"),"assessed":bool(review)})
    for row in local:
        if row.get("shared_deal_id"):
            continue
        review = latest.get((row.get("account_user_id"), row["credit_request_number"])) or {}
        records.append({"status": row["status"], "currency": "USD",
                        "amount": row["requested_amount"],
                        "score": review.get("overall_score"),"assessed":bool(review)})
    scores = []
    currencies = defaultdict(Decimal)
    statuses = Counter()
    for row in records:
        statuses[row["status"]] += 1
        try:
            score = Decimal(str(row["score"]))
            if score.is_finite() and 0 <= score <= 100:
                scores.append(score)
        except (InvalidOperation, TypeError):
            pass
        try:
            amount = Decimal(str(row["amount"]))
            if row["currency"] and amount.is_finite() and amount >= 0:
                currencies[row["currency"]] += amount
        except (InvalidOperation, TypeError):
            pass
    return {"active_requests": sum(statuses[s] for s in ("Pending", "In Review", "Escalated")),
            "total_requests": len(records), "assessed_requests": sum(r['assessed'] for r in records),
            "unassessed_requests": sum(not r['assessed'] for r in records),
            "policy_compliance": round(sum(scores) / len(scores), 1) if scores else None,
            "request_statuses": [{"label": label, "value": value} for label, value in sorted(statuses.items())],
            "requested_amounts": [{"currency": currency, "value": value} for currency, value in sorted(currencies.items())]}
