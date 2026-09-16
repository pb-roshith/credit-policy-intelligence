import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import SESSIONS
from app.routers import decision
from app.security import create_session
from app.services.scenario_simulator import calculate_metrics, recommended_case
from tests.user_store_helpers import delete_test_user


class ScenarioCalculationTest(unittest.TestCase):
    def setUp(self):
        self.inputs = {
            "facility_amount": 85,
            "collateral_coverage": 85,
            "risk_rating": "BB-",
            "pricing_bps": 325,
            "tenor_years": 7,
            "covenants": "Partial",
        }

    def test_all_metrics_and_sensitivity_are_calculated(self):
        result = calculate_metrics(self.inputs)
        self.assertEqual(set(result), {
            "expected_loss", "ecl_impact", "rwa_impact", "capital_impact",
            "concentration_impact", "risk_appetite_score", "assumptions", "sensitivity",
        })
        self.assertGreater(result["ecl_impact"], result["expected_loss"])
        self.assertAlmostEqual(result["capital_impact"], result["rwa_impact"] * 0.105, places=3)
        self.assertEqual(result["concentration_impact"], 8.5)
        self.assertGreaterEqual(result["risk_appetite_score"], 0)
        self.assertLessEqual(result["risk_appetite_score"], 100)
        self.assertEqual(len(result["sensitivity"]), 5)
        self.assertEqual(
            sorted(point["expected_loss"] for point in result["sensitivity"]),
            [point["expected_loss"] for point in result["sensitivity"]],
        )

    def test_modelled_mitigation_improves_risk(self):
        base = calculate_metrics(self.inputs, include_sensitivity=False)
        improved_inputs, improved = recommended_case(self.inputs)
        self.assertEqual(improved_inputs["covenants"], "Full")
        self.assertLess(improved["expected_loss"], base["expected_loss"])
        self.assertLess(improved["rwa_impact"], base["rwa_impact"])
        self.assertGreater(improved["risk_appetite_score"], base["risk_appetite_score"])


class ScenarioEndpointTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(decision.router)
        self.client = TestClient(app)
        self.session = create_session({
            "user_id": "isolation-test-" + uuid4().hex,
            "role": "credit_analyst",
        })
        self.headers = {"Authorization": "Bearer " + self.session["token"]}
        self.payload = {
            "scenario_name": "FY27 downside",
            "facility_amount": 85,
            "collateral_coverage": 85,
            "risk_rating": "BB-",
            "pricing_bps": 325,
            "tenor_years": 7,
            "covenants": "Partial",
        }

    def tearDown(self):
        self.client.close()
        SESSIONS.pop(self.session["token"], None)
        delete_test_user(self.session["user"]["user_id"])

    @patch("app.routers.decision.ScenarioRecommendationAgent.run")
    def test_run_saves_and_rejects_case_insensitive_duplicate(self, generate):
        generate.return_value = ("test-agent", ["One", "Two", "Three"])
        response = self.client.post("/api/decision-scenarios", json=self.payload, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["scenario_name"], "FY27 downside")
        self.assertEqual(len(body["recommendations"]), 3)
        self.assertIn("sensitivity", body["results"])

        scenarios = self.client.get("/api/decision-scenarios", headers=self.headers)
        self.assertEqual(scenarios.status_code, 200, scenarios.text)
        self.assertEqual(scenarios.json()[0]["scenario_name"], "FY27 downside")
        loaded = self.client.get(
            f"/api/decision-scenarios/{body['scenario_id']}", headers=self.headers
        )
        self.assertEqual(loaded.status_code, 200, loaded.text)
        self.assertEqual(loaded.json()["results"], body["results"])
        self.assertEqual(loaded.json()["recommendations"], ["One", "Two", "Three"])

        duplicate = self.client.post(
            "/api/decision-scenarios",
            json={**self.payload, "scenario_name": "  fy27 DOWNSIDE  "},
            headers=self.headers,
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertIn("choose another", duplicate.json()["detail"].lower())
        generate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
