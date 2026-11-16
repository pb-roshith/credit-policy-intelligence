import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from app.schemas import ComplianceReviewRequest, ComplianceCopilotRequest
from app.services.assessment_request import normalize_request_id, deal_assessment_context
from app.services.compliance_agent import latest_stored_compliance_review

class AssessmentRequestTests(unittest.TestCase):
    def test_shared_id_over_24_characters_is_accepted_and_preserved(self):
        value = "deal_" + "Ab12" * 7
        self.assertEqual(ComplianceReviewRequest(credit_request_number=value).credit_request_number,value)
        self.assertEqual(ComplianceCopilotRequest(credit_request_number=value,question="Explain finding").credit_request_number,value)
    def test_legacy_id_normalized(self):
        self.assertEqual(normalize_request_id(" cr-10241 "),"CR-10241")
    @patch("app.services.assessment_request.DealRetrievalAgent")
    def test_dossier_context_uses_actual_values_and_no_display_assumptions(self, agent):
        agent.return_value.run.return_value = {"deals":[{"id":"deal_AbC", "customer":"Borrower", "amount":125000, "currency":"INR", "status":"Draft", "intake":{"rating":"AA"}}]}
        user = {"user_id":"owner"}
        proposal = deal_assessment_context("deal_AbC", user)
        self.assertEqual(proposal["requested_amount"],125000)
        self.assertEqual(proposal["currency"],"INR")
        self.assertEqual(proposal["rating"],"AA")
        self.assertEqual(proposal["status"],"Pending")
        self.assertIsNone(proposal["exposure"])
        agent.return_value.run.assert_called_once_with(user)
    @patch("app.services.assessment_request.DealRetrievalAgent")
    def test_deals_from_other_accounts_cannot_be_used(self, agent):
        agent.return_value.run.return_value = {"deals":[]}
        with self.assertRaises(HTTPException) as error:
            deal_assessment_context("deal_other",{"user_id":"owner"})
        self.assertEqual(error.exception.status_code,404)
    @patch("app.services.compliance_agent.db_connection")
    def test_saved_review_keeps_shared_id_case(self, db):
        connection = db.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value = None
        self.assertIsNone(latest_stored_compliance_review("deal_AbC"))
        sql, params = connection.execute.call_args.args
        self.assertIn("COALESCE(source_request_id, credit_request_number)",sql)
        self.assertEqual(params,("deal_AbC",))

class ComplianceSubmissionTests(unittest.TestCase):
    @patch("app.services.semantic_assessment.run_rule_assessment")
    @patch("app.routers.compliance.latest_stored_compliance_review", return_value=None)
    def test_dropdown_dossier_id_submits_through_api(self, latest, assessment):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.routers.compliance import router
        from app.security import current_user
        user = {"user_id":"owner", "role":"credit_analyst"}
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[current_user] = lambda: user
        request_id = "deal_" + "Ab12" * 7
        assessment.return_value = {"agent":"Approved Policy Rule Assessment"}
        response = TestClient(app).post("/api/compliance-review/run",json={"credit_request_number":request_id,"recalculate":False})
        self.assertEqual(response.status_code,200)
        assessment.assert_called_once_with(request_id,"owner",user=user)

    @patch("app.services.semantic_assessment.run_rule_assessment")
    @patch("app.routers.compliance.latest_stored_compliance_review")
    def test_run_creates_new_review_and_leaves_historical_snapshot(self, latest, assessment):
        from app.routers.compliance import run_compliance_review
        latest.return_value = {"review_id":7,"rule_snapshots":[{"version":1}]}
        assessment.return_value = {"review_id":8,"rule_snapshots":[{"version":2}]}
        result = run_compliance_review(ComplianceReviewRequest(credit_request_number="deal_AbC"),{"user_id":"owner"})
        self.assertEqual(result["review_id"],8)
        assessment.assert_called_once_with("deal_AbC","owner",user={"user_id":"owner"})
        self.assertEqual(latest.return_value['rule_snapshots'],[{"version":1}])
