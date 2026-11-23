"""Canonical API integration tests; all test deal writes are rolled back."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.database import engine, SessionLocal, get_db
from app.models import Deal, User
from app.migrations import apply_additive_migrations
from app.routers.shared_deals import router
from app.schemas.deal import DealCreate
from app.services.new_deal_agent import IntakeAssessment


class SharedDealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_additive_migrations(engine)

    def setUp(self):
        self.db = SessionLocal()
        # Use a transient authenticated owner rather than changing a real account.
        self.owner = User(user_id="shared-deal-integration-owner", password_hash="unused",
                          role="relationship_manager", is_active=True, is_approved=True)
        self.other = User(user_id="shared-deal-integration-other", password_hash="unused",
                          role="relationship_manager", is_active=True, is_approved=True)
        self.db.add_all([self.owner, self.other])
        self.db.flush()
        self.commit_patch = patch.object(self.db, "commit", self.db.flush)
        self.commit_patch.start()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.headers = {"X-Shared-Deal-Key": settings.SHARED_DEAL_API_KEY,
                        "X-Shared-User-Id": self.owner.user_id}
        self.payload = {"customer": "Integration Test Borrower", "industry": "Manufacturing",
                        "geography": "US Northeast", "currency": "USD", "amount": 1000000,
                        "creation_request_id": "integration_request_0001"}
        response = SimpleNamespace(conversation_id="conversation-test", outputs=[
            SimpleNamespace(type="message.output", content=json.dumps({
                "summary": "Borrower requests a USD term loan.", "next_steps": ["Complete KYC."]
            }))])
        self.mistral_patch = patch("app.services.new_deal_agent.Mistral")
        self.mistral = self.mistral_patch.start()
        self.mistral.return_value.__enter__.return_value.beta.conversations.start.return_value = response
        self.agent_patch = patch("app.services.new_deal_agent.ensure_agent", return_value="agent-test")
        self.agent_patch.start()
        self.sync_patch = patch("app.routers.shared_deals.LibrarySyncService.sync_mcp_documents")
        self.sync_patch.start()

    def tearDown(self):
        self.sync_patch.stop()
        self.agent_patch.stop()
        self.mistral_patch.stop()
        self.commit_patch.stop()
        self.db.rollback()
        self.db.close()
        self.client.close()

    def test_retry_returns_one_deal_and_one_conversation(self):
        first = self.client.post("/api/shared/deals", headers=self.headers, json=self.payload)
        self.assertEqual(first.status_code, 201, first.text)
        second = self.client.post("/api/shared/deals", headers=self.headers, json=self.payload)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(self.db.query(Deal).filter_by(owner_user_id=self.owner.id).count(), 1)
        deal = self.db.query(Deal).filter_by(id=first.json()["id"]).one()
        self.assertEqual(len(deal.sections), 16)
        self.mistral.return_value.__enter__.return_value.beta.conversations.start.assert_called_once()
        visible = self.client.get("/api/shared/deals", headers=self.headers).json()
        self.assertEqual(visible[0]["intake"]["conversation_id"], "conversation-test")
        self.assertNotIn("input_hash", visible[0]["intake"])
        self.headers["X-Shared-User-Id"] = self.other.user_id
        self.assertEqual(self.client.get("/api/shared/deals", headers=self.headers).json(), [])

    def test_reused_request_id_with_changed_terms_is_rejected(self):
        self.assertEqual(self.client.post("/api/shared/deals", headers=self.headers, json=self.payload).status_code, 201)
        changed = {**self.payload, "amount": 2000000}
        self.assertEqual(self.client.post("/api/shared/deals", headers=self.headers, json=changed).status_code, 409)

    def test_authentication_and_role_checks_precede_agent(self):
        self.assertEqual(self.client.get("/api/shared/deals").status_code, 401)
        missing = {**self.headers, "X-Shared-User-Id": "missing-account"}
        self.assertEqual(self.client.post("/api/shared/deals", headers=missing, json=self.payload).status_code, 403)
        self.owner.role = "credit_analyst"
        self.db.flush()
        self.assertEqual(self.client.post("/api/shared/deals", headers=self.headers, json=self.payload).status_code, 403)
        self.mistral.assert_not_called()

    def test_invalid_document_counts_rejected(self):
        invalid = {**self.payload, "total_required_documents": 1, "uploaded_required_documents": 2}
        self.assertEqual(self.client.post("/api/shared/deals", headers=self.headers, json=invalid).status_code, 422)
        self.mistral.assert_not_called()

    def test_company_lookup_reuses_dossier_service_and_verified_owner(self):
        from unittest.mock import AsyncMock
        with patch("app.routers.mcp.list_companies", new_callable=AsyncMock) as companies, \
             patch("app.routers.mcp.get_company_details", new_callable=AsyncMock) as details:
            companies.return_value = [{"name": "Example Company", "document_count": 3}]
            details.return_value = {"industry": "Manufacturing", "geography": "India"}
            result = self.client.get("/api/shared/deals/companies", headers=self.headers)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()[0]["name"], "Example Company")
            self.assertEqual(companies.call_args.kwargs["current_user"].user_id, self.owner.user_id)
            result = self.client.post("/api/shared/deals/companies/details", headers=self.headers, json={"name": "Example Company"})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(details.call_args.kwargs["company_name"], "Example Company")
            self.assertEqual(details.call_args.kwargs["current_user"].user_id, self.owner.user_id)
            self.assertEqual(self.client.get("/api/shared/deals/companies").status_code, 401)

    def test_agent_failure_creates_no_deal(self):
        self.mistral.return_value.__enter__.return_value.beta.conversations.start.side_effect = RuntimeError("upstream unavailable")
        result = self.client.post("/api/shared/deals", headers=self.headers, json=self.payload)
        self.assertEqual(result.status_code, 502)
        self.assertNotIn("upstream unavailable", result.text)
        self.assertEqual(self.db.query(Deal).filter_by(customer=self.payload["customer"]).count(), 0)

    def test_dossier_credentials_work_without_creating_a_dossier_session(self):
        from app.auth import hash_password
        from app.models import AuthSession
        self.owner.password_hash = hash_password("SyntheticOnly!123456")
        self.db.flush()
        response = self.client.post("/api/shared/deals/identity/authenticate", headers=self.headers,
                                    json={"user_id": self.owner.user_id.upper(), "password": "SyntheticOnly!123456"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["user_id"], self.owner.user_id)
        self.assertEqual(self.db.query(AuthSession).filter_by(user_id=self.owner.id).count(), 0)
        bad = self.client.post("/api/shared/deals/identity/authenticate", headers=self.headers,
                               json={"user_id": self.owner.user_id, "password": "incorrect"})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(self.owner.failed_login_attempts, 1)
        self.owner.is_locked = True
        self.db.flush()
        locked = self.client.post("/api/shared/deals/identity/authenticate", headers=self.headers,
                                  json={"user_id": self.owner.user_id, "password": "SyntheticOnly!123456"})
        self.assertEqual(locked.status_code, 423)

    def test_analyst_sees_both_managers_five_deals_in_list_and_retrieval(self):
        ids = []
        for manager, count in [(self.owner, 3), (self.other, 2)]:
            headers = {**self.headers, "X-Shared-User-Id": manager.user_id}
            for index in range(count):
                payload = {**self.payload, "creation_request_id": f"visibility_{manager.user_id}_{index}"}
                response = self.client.post("/api/shared/deals", headers=headers, json=payload)
                self.assertEqual(response.status_code, 201)
                ids.append(response.json()["id"])
            visible = self.client.get("/api/shared/deals", headers=headers).json()
            self.assertEqual(len(visible), count)
        analyst = User(user_id="shared-deal-integration-analyst", password_hash="unused",
                       role="credit_analyst", is_active=True, is_approved=True)
        self.db.add(analyst)
        self.db.flush()
        headers = {**self.headers, "X-Shared-User-Id": analyst.user_id}
        visible = self.client.get("/api/shared/deals", headers=headers).json()
        self.assertTrue(set(ids).issubset({deal["id"] for deal in visible}))
        with patch("app.services.deal_retrieval_agent.Mistral", side_effect=RuntimeError("offline")):
            retrieved = self.client.post("/api/shared/deals/retrieve", headers=headers, json={}).json()
        self.assertTrue(set(ids).issubset({deal["id"] for deal in retrieved["deals"]}))

    def test_retrieval_agent_returns_exact_owned_deals_and_cannot_change_owner(self):
        created = self.client.post("/api/shared/deals", headers=self.headers, json=self.payload).json()
        call = SimpleNamespace(type="function.call", name="list_owned_deals", arguments="{}", tool_call_id="call-test")
        with patch("app.services.deal_retrieval_agent.Mistral") as client, \
             patch("app.services.deal_retrieval_agent.ensure_retrieval_agent", return_value="retrieval-test"):
            sdk = client.return_value.__enter__.return_value
            sdk.beta.conversations.start.return_value = SimpleNamespace(outputs=[call], conversation_id="retrieval-conversation")
            result = self.client.post("/api/shared/deals/retrieve", headers=self.headers, json={}).json()
            self.assertEqual(result["status"], "agent")
            self.assertEqual([deal["id"] for deal in result["deals"]], [created["id"]])
            # A model-supplied owner is never allowed to control the query.
            call.arguments = '{"user_id": "another-user"}'
            result = self.client.post("/api/shared/deals/retrieve", headers=self.headers, json={}).json()
            self.assertEqual(result["status"], "direct")
            self.assertEqual([deal["id"] for deal in result["deals"]], [created["id"]])
            self.headers["X-Shared-User-Id"] = self.other.user_id
            self.assertEqual(self.client.post("/api/shared/deals/retrieve", headers=self.headers, json={}).json()["deals"], [])


if __name__ == "__main__":
    unittest.main()
