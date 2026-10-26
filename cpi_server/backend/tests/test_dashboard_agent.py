from contextlib import nullcontext
from types import SimpleNamespace
import json
import unittest
from unittest.mock import MagicMock, patch

import httpx
from fastapi import HTTPException
from mistralai.client.errors import SDKError

from app.services.dashboard_agent import PortfolioInsightsAgent


def provider_error(status):
    return SDKError("API error occurred", httpx.Response(status, text="Agent was not found"))


class DashboardAgentTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.start = self.client.beta.conversations.start
        self.points = [f"Observation {i}" for i in range(5)]
        self.response = SimpleNamespace(outputs=[SimpleNamespace(
            type="message.output", content=json.dumps({"insights": self.points}))])
        self.start.return_value = self.response
        self.snapshot = {"generated_at": "2026-10-16T04:00:00Z", "metrics": {}}
        self.mistral = patch("app.services.dashboard_agent.Mistral")
        self.mistral.start().return_value.__enter__.return_value = self.client
        self.addCleanup(self.mistral.stop)
        self.observation = patch("app.services.dashboard_agent.observe_ai", side_effect=lambda *a, **k: nullcontext({}))
        self.observation.start()
        self.addCleanup(self.observation.stop)

    def test_missing_agent_is_replaced_and_insights_saved_with_replacement(self):
        self.start.side_effect = [provider_error(404), self.response]
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {"insights": self.points}
        with patch.object(PortfolioInsightsAgent, "_agent_id", side_effect=["missing", "replacement"]) as resolve, \
             patch("app.services.dashboard_agent.run_db_transaction", side_effect=lambda operation: operation(connection)):
            result = PortfolioInsightsAgent().run(self.snapshot, "user-1")
        self.assertEqual(result["insights"], self.points)
        self.assertEqual(resolve.call_args_list[1].kwargs, {"missing_agent_id": "missing"})
        self.assertEqual([call.kwargs["agent_id"] for call in self.start.call_args_list], ["missing", "replacement"])
        self.assertEqual(connection.execute.call_args.args[1][2], "replacement")

    def test_other_provider_errors_do_not_replace_agent_or_save(self):
        for status in (401, 429, 500):
            with self.subTest(status=status):
                self.start.side_effect = provider_error(status)
                with patch.object(PortfolioInsightsAgent, "_agent_id", return_value="existing") as resolve, \
                     patch("app.services.dashboard_agent.run_db_transaction") as persist:
                    with self.assertRaises(HTTPException) as caught:
                        PortfolioInsightsAgent().run(self.snapshot, "user-1")
                    self.assertEqual(caught.exception.status_code, 502)
                    resolve.assert_called_once_with()
                    persist.assert_not_called()

    def test_recovery_is_bounded_to_one_replacement(self):
        self.start.side_effect = provider_error(404)
        with patch.object(PortfolioInsightsAgent, "_agent_id", side_effect=["missing", "replacement"]) as resolve, \
             patch("app.services.dashboard_agent.run_db_transaction") as persist:
            with self.assertRaises(HTTPException):
                PortfolioInsightsAgent().run(self.snapshot, "user-1")
            self.assertEqual(resolve.call_count, 2)
            self.assertEqual(self.start.call_count, 2)
            persist.assert_not_called()

    def test_spending_limit_is_reported_without_exposing_provider_response(self):
        self.start.side_effect = provider_error(402)
        with patch.object(PortfolioInsightsAgent, "_agent_id", return_value="existing"), \
             patch("app.services.dashboard_agent.run_db_transaction") as persist:
            with self.assertRaises(HTTPException) as caught:
                PortfolioInsightsAgent().run(self.snapshot, "user-1")
            self.assertEqual(caught.exception.status_code, 402)
            self.assertIn("workspace spending limit", caught.exception.detail)
            self.assertNotIn("Agent was not found", caught.exception.detail)
            persist.assert_not_called()

    def test_concurrent_recovery_reuses_an_already_replaced_agent(self):
        with patch("app.services.dashboard_agent.MISTRAL_API_KEY", "test-key"), \
             patch("app.services.dashboard_agent.shared_policy_connection") as database:
            database.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {
                "mistral_dashboard_agent_id": "replacement"}
            self.assertEqual(PortfolioInsightsAgent()._agent_id(missing_agent_id="missing"), "replacement")
            self.client.beta.agents.create.assert_not_called()

    def test_stale_configuration_is_replaced_under_lock(self):
        self.client.beta.agents.create.return_value.id = "replacement"
        with patch("app.services.dashboard_agent.MISTRAL_API_KEY", "test-key"), \
             patch("app.services.dashboard_agent.shared_policy_connection") as database:
            connection = database.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.return_value = {"mistral_dashboard_agent_id": "missing"}
            self.assertEqual(PortfolioInsightsAgent()._agent_id(missing_agent_id="missing"), "replacement")
            self.client.beta.agents.create.assert_called_once()
            self.assertEqual(connection.execute.call_args.args[1], ("replacement",))

    def test_key_from_another_account_replaces_inaccessible_agent_and_saves_id(self):
        self.client.beta.agents.get.side_effect = provider_error(404)
        self.client.beta.agents.create.return_value.id = "new-account-agent"
        with patch("app.services.dashboard_agent.MISTRAL_API_KEY", "new-account-key"), \
             patch("app.services.dashboard_agent.shared_policy_connection") as database:
            connection = database.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.return_value = {"mistral_dashboard_agent_id": "old-account-agent"}
            self.assertEqual(PortfolioInsightsAgent()._agent_id(), "new-account-agent")
            self.client.beta.agents.get.assert_called_once_with(agent_id="old-account-agent")
            self.client.beta.agents.create.assert_called_once()
            self.assertEqual(connection.execute.call_args.args[1], ("new-account-agent",))

    def test_existing_accessible_agent_is_reused(self):
        with patch("app.services.dashboard_agent.MISTRAL_API_KEY", "test-key"), \
             patch("app.services.dashboard_agent.shared_policy_connection") as database:
            connection = database.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.return_value = {"mistral_dashboard_agent_id": "existing"}
            self.assertEqual(PortfolioInsightsAgent()._agent_id(), "existing")
            self.client.beta.agents.get.assert_called_once_with(agent_id="existing")
            self.client.beta.agents.create.assert_not_called()
            self.assertEqual(connection.execute.call_count, 2)

    def test_agent_lookup_auth_and_transient_failures_preserve_saved_id(self):
        for status in (401, 429, 500):
            with self.subTest(status=status), \
                 patch("app.services.dashboard_agent.MISTRAL_API_KEY", "test-key"), \
                 patch("app.services.dashboard_agent.shared_policy_connection") as database:
                connection = database.return_value.__enter__.return_value
                connection.execute.return_value.fetchone.return_value = {"mistral_dashboard_agent_id": "existing"}
                self.client.beta.agents.get.side_effect = provider_error(status)
                with self.assertRaises(SDKError):
                    PortfolioInsightsAgent()._agent_id()
                self.client.beta.agents.create.assert_not_called()
                self.assertEqual(connection.execute.call_count, 2)

    def test_first_use_creates_and_saves_an_agent(self):
        self.client.beta.agents.create.return_value.id = "first-agent"
        with patch("app.services.dashboard_agent.MISTRAL_API_KEY", "test-key"), \
             patch("app.services.dashboard_agent.shared_policy_connection") as database:
            connection = database.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.return_value = None
            self.assertEqual(PortfolioInsightsAgent()._agent_id(), "first-agent")
            self.client.beta.agents.get.assert_not_called()
            self.client.beta.agents.create.assert_called_once()
            self.assertEqual(connection.execute.call_args.args[1], ("first-agent",))
