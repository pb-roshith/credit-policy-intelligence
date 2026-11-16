import unittest
from app.services.semantic_assessment import ENGINE_VERSION
def semantic(score):return {'overall_score':score,'assessment_scope':'current-semantic-graph','engine_version':ENGINE_VERSION}
from app.services.dashboard_requests import request_totals


class DashboardRequestTests(unittest.TestCase):
    def test_five_deals_are_counted_without_assumed_scores_or_currency_conversion(self):
        deals = [{"id": str(i), "status": "Draft", "currency": "INR", "amount": 1000} for i in range(5)]
        result = request_totals(deals, [], [])
        self.assertEqual(result["active_requests"], 5)
        self.assertEqual(result["unassessed_requests"], 5)
        self.assertIsNone(result["policy_compliance"])
        self.assertEqual(result["requested_amounts"], [{"currency": "INR", "value": 5000}])

    def test_linked_requests_are_deduplicated_and_latest_saved_review_is_used(self):
        deals = [{"id": "deal_a", "status": "In Progress", "currency": "INR", "amount": 1000}]
        local = [
            {"shared_deal_id": "deal_a", "credit_request_number": "CR-1", "compliance_score": 60},
            {"shared_deal_id": None, "credit_request_number": "CR-2", "status": "Approved", "requested_amount": 100, "compliance_score": 90},
            {"shared_deal_id": "inaccessible", "credit_request_number": "CR-3", "compliance_score": 10},
        ]
        reviews = [{"request_id": "deal_a", "review": semantic(80)}]
        result = request_totals(deals, local, reviews)
        self.assertEqual(result["total_requests"], 2)
        self.assertEqual(result["active_requests"], 1)
        self.assertEqual(result["policy_compliance"], 80)
        self.assertEqual(result["assessed_requests"], 1)
        self.assertEqual(result["requested_amounts"], [{"currency": "INR", "value": 1000}, {"currency": "USD", "value": 100}])

    def test_missing_and_invalid_scores_are_not_zero_compliance(self):
        deals = [{"id": "deal_a", "status": "Exported", "currency": "USD", "amount": 1}]
        result = request_totals(deals, [], [{"request_id": "deal_a", "review": {"overall_score": "NaN"}}])
        self.assertEqual(result["active_requests"], 0)
        self.assertIsNone(result["policy_compliance"])

    def test_identical_numbers_from_two_managers_keep_their_own_scores(self):
        local = [{"account_user_id": owner, "shared_deal_id": None,
                  "credit_request_number": "CR-1", "status": "Pending",
                  "requested_amount": 100, "compliance_score": 50}
                 for owner in ("manager_a", "manager_b")]
        reviews = [{"account_user_id": owner, "request_id": "CR-1", "review": semantic(score)}
                   for owner, score in (("manager_a", 60), ("manager_b", 100))]
        result = request_totals([], local, reviews)
        self.assertEqual(result["total_requests"], 2)
        self.assertEqual(result["policy_compliance"], 80)
