import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from app.services.shared_deals import compliance_payload, call_shared_deals
from app.services.deal_projection import persist_deal_projection


class SharedDealTests(unittest.TestCase):
    def setUp(self):
        self.deal = {"id": "deal_shared_test", "customer": "Test Borrower", "industry": "Manufacturing",
                     "geography": "US Northeast", "currency": "USD", "amount": 1000000,
                     "facility": "Term Loan", "status": "Draft", "intake": {
                         "rating": "BBB", "collateral_coverage": 120,
                         "total_required_documents": 4, "uploaded_required_documents": 2}}

    def test_projection_preserves_original_amount_and_inputs(self):
        payload = compliance_payload(self.deal)
        self.assertEqual(payload.requested_amount, 1000000)
        self.assertEqual(payload.rating, "BBB")
        self.assertEqual(payload.total_required_documents, 4)
        self.assertEqual(payload.status, "Pending")

    def test_non_usd_or_unsupported_deals_remain_display_only(self):
        for changes in ({"currency": "INR"}, {"geography": "Chennai"}, {"amount": 0}, {"amount": 12.5}):
            self.assertIsNone(compliance_payload({**self.deal, **changes}))

    def test_existing_projection_is_reused_without_second_insert(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {"shared_deal_id": "deal_shared_test"}
        with patch("app.services.deal_projection.db_connection") as db, \
             patch("app.services.deal_projection.public_credit_request", side_effect=lambda row: row):
            db.return_value.__enter__.return_value = connection
            result = persist_deal_projection(compliance_payload(self.deal), "deal_shared_test")
        self.assertEqual(result["shared_deal_id"], "deal_shared_test")
        self.assertFalse(any("INSERT" in args.args[0] for args in connection.execute.call_args_list))

    def test_consumer_uses_authenticated_identity_and_returns_canonical_id(self):
        import io, json
        with patch("app.services.shared_deals.SHARED_DEAL_API_KEY", "service-test-key"), \
             patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = io.BytesIO(json.dumps(self.deal).encode())
            result = call_shared_deals({"user_id": "verified-owner"}, {"customer": "Test Borrower", "user_id": "attacker"})
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.get_header("X-shared-user-id"), "verified-owner")
            self.assertEqual(result["id"], "deal_shared_test")

    def test_missing_service_key_fails_closed(self):
        with patch("app.services.shared_deals.SHARED_DEAL_API_KEY", ""):
            with self.assertRaises(HTTPException) as error:
                call_shared_deals({"user_id": "verified-owner"})
            self.assertEqual(error.exception.status_code, 503)

    def test_invalid_shared_responses_are_rejected_before_use(self):
        import io, json
        cases = (
            ("", [{**self.deal, "amount": "1000000"}]),
            ("/identity/authenticate", {"found": True, "user_id": "owner"}),
            ("/identity", {"user_id": "other-owner", "role": "credit_analyst", "credential_version": 1}),
            ("/identity/reset-password", {"unexpected": "response"}),
            ("/identity/password-policy", {
                "min_length": 12, "max_length": 8, "min_uppercase": 1,
                "min_lowercase": 1, "min_digits": 1, "min_special": 1,
            }),
        )
        with patch("app.services.shared_deals.SHARED_DEAL_API_KEY", "service-test-key"), \
             patch("urllib.request.build_opener") as opener:
            for path, payload in cases:
                with self.subTest(path=path), self.assertRaises(HTTPException) as error:
                    opener.return_value.open.return_value = io.BytesIO(json.dumps(payload).encode())
                    call_shared_deals({"user_id": "owner"}, path=path)
                self.assertEqual(error.exception.status_code, 502)

    def test_cpi_deal_creation_is_forbidden(self):
        from app.routers.requests import create_shared_deal
        with self.assertRaises(HTTPException) as error:
            create_shared_deal({}, {"user_id": "owner", "role": "relationship_manager"})
        self.assertEqual(error.exception.status_code, 403)

    def test_retrieval_uses_the_agent_read_endpoint(self):
        from app.services.deal_retrieval import DealRetrievalAgent
        with patch("app.services.deal_retrieval.call_shared_deals") as shared:
            shared.return_value = {"deals": [self.deal], "status": "agent"}
            user = {"user_id": "owner", "dossier_user_id": "canonical-owner"}
            self.assertEqual(DealRetrievalAgent().run(user)["deals"], [self.deal])
            shared.assert_called_once_with(user, {}, path="/retrieve")

    def test_bad_dossier_password_never_falls_back_to_local_credentials(self):
        from app.services.dossier_identity import authenticate_dossier_user
        with patch("app.services.dossier_identity.SHARED_DEAL_API_KEY", "configured"), \
             patch("app.services.dossier_identity.call_shared_deals", side_effect=HTTPException(401, "Invalid password")), \
             patch("app.services.dossier_identity.db_connection") as db:
            with self.assertRaises(HTTPException) as error:
                authenticate_dossier_user("SKY", "incorrect")
            self.assertEqual(error.exception.status_code, 401)
            db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
