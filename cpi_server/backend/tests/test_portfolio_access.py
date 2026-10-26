import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.dashboard import router
from app.security import current_user


class PortfolioAccessTests(unittest.TestCase):
    def setUp(self):
        self.user = {"user_id": "test-user", "role": "relationship_manager"}
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[current_user] = lambda: self.user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_other_roles_cannot_read_analytics_or_call_chat(self):
        with patch("app.routers.dashboard.db_connection") as database, \
             patch("app.routers.dashboard.PortfolioChatAgent") as agent:
            for role in ("relationship_manager", "admin"):
                self.user["role"] = role
                self.assertEqual(self.client.get("/api/portfolio").status_code, 403)
                self.assertEqual(self.client.post("/api/portfolio/chat", json={
                    "question": "What is the sector exposure?", "history": []
                }).status_code, 403)
            database.assert_not_called()
            agent.assert_not_called()

    def test_analyst_can_read_analytics_and_call_chat(self):
        self.user["role"] = "credit_analyst"
        with patch("app.routers.dashboard.db_connection") as database:
            database.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {"value": "now"}
            database.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = []
            self.assertEqual(self.client.get("/api/portfolio").status_code, 200)
        with patch("app.routers.dashboard.portfolio", return_value={}), \
             patch("app.routers.dashboard.PortfolioChatAgent") as agent:
            agent.return_value.run.return_value = {"answer": "Test response"}
            self.assertEqual(self.client.post("/api/portfolio/chat", json={
                "question": "What is the sector exposure?", "history": []
            }).status_code, 200)
            agent.return_value.run.assert_called_once()
