"""Missing workspace agents are replaced without losing their saved records."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from mistralai.client.errors import SDKError

from app.services.mistral_library_service import MistralLibraryService
from app.services.new_deal_agent import ensure_agent
from app.services.deal_retrieval_agent import ensure_retrieval_agent


def provider_error(status):
    return SDKError('Provider failure', httpx.Response(status))


class StartupAgentRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def run_init(self, db, client):
        with patch('app.services.mistral_library_service._get_client', return_value=client), \
             patch('app.services.mistral_library_service.get_tracer', return_value=None), \
             patch('app.services.deal_service.DEFAULT_SECTIONS', [
                 {'section_key': 'test-section', 'title': 'Test Section'}]), \
             patch('app.services.mistral_library_service.get_instructions', return_value='Section instructions'):
            await MistralLibraryService.initialize_global_agents(db)

    async def test_missing_section_and_orchestration_agents_are_replaced_and_saved(self):
        db = MagicMock()
        section = SimpleNamespace(agent_id='old-section')
        orchestration = SimpleNamespace(agent_id='old-orchestration')
        db.query.return_value.filter.return_value.first.side_effect = [section, orchestration]
        client = MagicMock()
        client.beta.agents.update_async = AsyncMock(side_effect=provider_error(404))
        client.beta.agents.create_async = AsyncMock(side_effect=[
            SimpleNamespace(id='new-section'), SimpleNamespace(id='new-orchestration')])
        await self.run_init(db, client)
        self.assertEqual(section.agent_id, 'new-section')
        self.assertEqual(orchestration.agent_id, 'new-orchestration')
        self.assertEqual(db.commit.call_count, 2)
        db.add.assert_not_called()

    async def test_accessible_agents_are_reused(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(agent_id='existing')
        client = MagicMock()
        client.beta.agents.update_async = AsyncMock()
        client.beta.agents.create_async = AsyncMock()
        await self.run_init(db, client)
        self.assertEqual(client.beta.agents.update_async.await_count, 2)
        client.beta.agents.create_async.assert_not_awaited()

    async def test_first_start_creates_and_saves_agents(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        client = MagicMock()
        client.beta.agents.create_async = AsyncMock(return_value=SimpleNamespace(id='new'))
        await self.run_init(db, client)
        self.assertEqual(db.add.call_count, 2)
        self.assertEqual(db.commit.call_count, 2)

    async def test_auth_quota_and_server_failures_do_not_create_replacements(self):
        for status in (401, 402, 429, 500):
            with self.subTest(status=status):
                db = MagicMock()
                client = MagicMock()
                client.beta.agents.update_async = AsyncMock(side_effect=provider_error(status))
                client.beta.agents.create_async = AsyncMock()
                with self.assertRaises(SDKError):
                    await self.run_init(db, client)
                client.beta.agents.create_async.assert_not_awaited()
                db.commit.assert_not_called()

    async def test_partial_startup_saves_successful_replacements_before_later_failure(self):
        db = MagicMock()
        section = SimpleNamespace(agent_id='old-section')
        orchestration = SimpleNamespace(agent_id='old-orchestration')
        db.query.return_value.filter.return_value.first.side_effect = [section, orchestration]
        client = MagicMock()
        client.beta.agents.update_async = AsyncMock(side_effect=provider_error(404))
        client.beta.agents.create_async = AsyncMock(side_effect=[SimpleNamespace(id='new-section'), provider_error(500)])
        with self.assertRaises(SDKError):
            await self.run_init(db, client)
        self.assertEqual(section.agent_id, 'new-section')
        self.assertEqual(orchestration.agent_id, 'old-orchestration')
        db.commit.assert_called_once()


class SharedAgentRecoveryTests(unittest.TestCase):
    def test_shared_agents_replace_missing_ids_without_duplicating_rows(self):
        for ensure in (ensure_agent, ensure_retrieval_agent):
            with self.subTest(feature=ensure.__name__):
                db, client = MagicMock(), MagicMock()
                existing = SimpleNamespace(agent_id='old')
                db.query.return_value.filter_by.return_value.first.side_effect = [existing, None]
                client.beta.agents.get.side_effect = provider_error(404)
                client.beta.agents.create.return_value.id = 'replacement'
                self.assertEqual(ensure(db, client), 'replacement')
                self.assertEqual(existing.agent_id, 'replacement')
                db.add.assert_not_called()
                db.flush.assert_called_once()
