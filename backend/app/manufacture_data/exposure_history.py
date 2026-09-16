from datetime import date, timedelta
import re
import secrets
from fastapi import APIRouter, Depends, HTTPException
from ..config import BORROWER_PREFIXES, BORROWER_SUFFIXES, INDUSTRY_FACILITIES, RATINGS, REQUEST_STATUSES
from ..database import db_connection, resolve_borrower
from ..schemas import CreateCreditRequest, GenerateBorrowerExposureRequest, GenerateCreditRequestsRequest, GeneratePolicyControlsRequest
from ..security import current_user
from ..services.compliance_scoring import calculate_compliance_score, persist_compliance_result

router = APIRouter(prefix="/api/data-manufacturing", tags=["data manufacturing"])

@router.post("/borrower-exposure-history", status_code=201)
def generate_borrower_exposure_history(payload: GenerateBorrowerExposureRequest, user: dict = Depends(current_user)):
    with db_connection() as connection:
        facilities = connection.execute("""
            SELECT credit_request_number, borrower_id, borrower_name, exposure, requested_amount, facility
            FROM credit_requests
            ORDER BY borrower_name, credit_request_number
        """).fetchall()
        if not facilities:
            raise HTTPException(status_code=422, detail="Generate credit requests before generating borrower exposure history")

        generated_count = 0
        profile_counts = {"Current": 0, "Delayed": 0, "Defaulted": 0}
        borrower_names = list(dict.fromkeys(row["borrower_id"] for row in facilities))
        borrower_profiles = {}
        for borrower_index, borrower_name in enumerate(borrower_names):
            profile_position = borrower_index % 10
            profile = "Current" if profile_position < 6 else "Delayed" if profile_position < 9 else "Defaulted"
            borrower_profiles[borrower_name] = profile
            profile_counts[profile] += 1

        for facility in facilities:
            profile = borrower_profiles[facility["borrower_id"]]
            original_exposure = max(facility["exposure"], facility["requested_amount"])
            outstanding_exposure = original_exposure
            scheduled_payment = max(500_000, original_exposure // max(12, payload.records_per_borrower + 6))
            facility_reference = f"FAC-{facility['credit_request_number'].removeprefix('CR-')}"

            for period in range(payload.records_per_borrower):
                months_ago = payload.records_per_borrower - period - 1
                current_month = date.today().year * 12 + date.today().month - 1
                reporting_month_index = current_month - months_ago
                reporting_month = date(reporting_month_index // 12, reporting_month_index % 12 + 1, 1)
                payment_status = "Current"
                days_past_due = 0
                actual_payment = min(scheduled_payment, outstanding_exposure)
                if profile == "Delayed" and (period == payload.records_per_borrower - 1 or period % 3 == 2):
                    payment_status = "Delayed"
                    days_past_due = 15 + secrets.randbelow(46)
                    actual_payment = min(outstanding_exposure, scheduled_payment // 2)
                elif profile == "Defaulted" and period >= payload.records_per_borrower // 2:
                    payment_status = "Defaulted"
                    days_past_due = 90 + (period - payload.records_per_borrower // 2) * 30 + secrets.randbelow(16)
                    actual_payment = 0
                outstanding_exposure = max(0, outstanding_exposure - actual_payment)

                connection.execute("""
                    INSERT INTO borrower_exposure_history (
                        borrower_id, facility_reference, facility_type,
                        reporting_month, original_exposure, scheduled_payment, actual_payment,
                        outstanding_exposure, days_past_due, payment_status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, borrower_id, facility_reference, reporting_month) DO UPDATE SET
                        original_exposure = EXCLUDED.original_exposure,
                        scheduled_payment = EXCLUDED.scheduled_payment,
                        actual_payment = EXCLUDED.actual_payment,
                        outstanding_exposure = EXCLUDED.outstanding_exposure,
                        days_past_due = EXCLUDED.days_past_due,
                        payment_status = EXCLUDED.payment_status
                """, (
                    facility["borrower_id"], facility_reference,
                    facility["facility"], reporting_month, original_exposure, scheduled_payment,
                    actual_payment, outstanding_exposure, days_past_due, payment_status,
                ))
                generated_count += 1

    return {
        "message": f"Generated {generated_count} borrower exposure records",
        "borrower_count": len(borrower_names),
        "facility_count": len(facilities),
        "records_per_borrower": payload.records_per_borrower,
        "record_count": generated_count,
        "borrower_profiles": profile_counts,
        "generated_by": user["user_id"],
    }
