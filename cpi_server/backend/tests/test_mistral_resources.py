from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import nullcontext
from types import SimpleNamespace
import json
import unittest
from unittest.mock import MagicMock, patch

import httpx
from mistralai.client.errors import SDKError

from app.services.portfolio_agent import PortfolioChatAgent
from app.services.scenario_simulator import ScenarioRecommendationAgent
from app.services.compliance_agent import GenerativeComplianceReviewAgent
from app.manufacture_data.policy_generation_service import _resources
from app.routers.policies import policy_copilot_chat
from app.schemas import PolicyCopilotRequest


def missing():
    return SDKError('Not found', httpx.Response(404))


class AgentRecoveryTests(unittest.TestCase):
    def test_all_other_hosted_agents_validate_and_replace_saved_ids(self):
        cases = [
            ('app.services.portfolio_agent', PortfolioChatAgent, 'mistral_portfolio_agent_id'),
            ('app.services.scenario_simulator', ScenarioRecommendationAgent, 'mistral_simulator_agent_id'),
            ('app.services.compliance_agent', GenerativeComplianceReviewAgent, 'mistral_compliance_agent_id'),
        ]
        for module, factory, column in cases:
            for exists in (True, False):
                with self.subTest(feature=column, exists=exists), \
                     patch(module + '.MISTRAL_API_KEY', 'new-account-key'), \
                     patch(module + '.shared_policy_connection') as database, \
                     patch(module + '.Mistral') as mistral, \
                     patch('app.services.compliance_agent._resources', return_value=('current-library', 'policy-agent')):
                    connection = database.return_value.__enter__.return_value
                    connection.execute.return_value.fetchone.return_value = {column: 'saved-id'}
                    client = mistral.return_value.__enter__.return_value
                    client.beta.agents.create.return_value.id = 'replacement-id'
                    if not exists:
                        client.beta.agents.get.side_effect = missing()
                    result = factory()._agent_id()
                    self.assertEqual(result, 'saved-id' if exists else 'replacement-id')
                    client.beta.agents.get.assert_called_once_with(agent_id='saved-id')
                    if exists:
                        client.beta.agents.create.assert_not_called()
                    else:
                        client.beta.agents.create.assert_called_once()
                        self.assertEqual(connection.execute.call_args.args[1], ('replacement-id',))


class PolicyResourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.beta.libraries.create.return_value.id = 'new-library'
        self.client.beta.agents.create.return_value.id = 'new-agent'
        self.database = MagicMock()
        self.connection = self.database.return_value.__enter__.return_value
        self.connection.execute.return_value.fetchone.return_value = {
            'mistral_library_id': 'old-library', 'mistral_agent_id': 'old-agent'}
        self.connection.execute.return_value.fetchall.return_value = []

    def test_account_switch_recreates_library_and_agent_and_restores_policy_sources(self):
        self.client.beta.libraries.get.side_effect = missing()
        self.client.beta.agents.get.side_effect = missing()
        self.client.beta.libraries.documents.upload.return_value.id = 'new-document'
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'policy.txt'
            source.write_text('Saved policy source', encoding='utf-8')
            self.connection.execute.return_value.fetchall.return_value = [
                {'policy_id': 1, 'file_name': source.name, 'local_pdf_path': str(source)}]
            with patch('app.manufacture_data.policy_generation_service._wait_for_document') as wait:
                self.assertEqual(_resources(self.client, self.database, 'model'), ('new-library', 'new-agent'))
            wait.assert_called_once_with(self.client, 'new-library', 'new-document')
            self.assertEqual(self.client.beta.agents.create.call_args.kwargs['tools'],
                             [{'type': 'document_library', 'library_ids': ['new-library']}])
            parameters = [call.args[1] for call in self.connection.execute.call_args_list if len(call.args) > 1]
            self.assertIn(('new-library',), parameters)
            self.assertIn(('new-agent',), parameters)
            self.assertIn(('new-document', 'new-library', 'new-agent', 1), parameters)

    def test_existing_resources_are_reused_and_agent_library_binding_is_repaired(self):
        self.assertEqual(_resources(self.client, self.database, 'model'), ('old-library', 'old-agent'))
        self.client.beta.libraries.create.assert_not_called()
        self.client.beta.agents.create.assert_not_called()
        self.client.beta.agents.update.assert_called_once_with(
            agent_id='old-agent', tools=[{'type': 'document_library', 'library_ids': ['old-library']}])

    def test_provider_auth_or_quota_failure_does_not_replace_resources(self):
        for status in (401, 402, 429, 500):
            with self.subTest(status=status):
                self.client.beta.libraries.get.side_effect = SDKError('Provider failure', httpx.Response(status))
                with self.assertRaises(SDKError):
                    _resources(self.client, self.database, 'model')
                self.client.beta.libraries.create.assert_not_called()
                self.client.beta.agents.create.assert_not_called()

    def test_partial_restore_resumes_into_existing_library(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'remaining.txt'
            source.write_text('Remaining policy', encoding='utf-8')
            self.connection.execute.return_value.fetchall.return_value = [
                {'policy_id': 2, 'file_name': source.name, 'local_pdf_path': str(source)}]
            with patch('app.manufacture_data.policy_generation_service._wait_for_document'):
                _resources(self.client, self.database, 'model')
            self.client.beta.libraries.create.assert_not_called()
            self.client.beta.libraries.documents.upload.assert_called_once()

    def test_missing_local_source_fails_instead_of_claiming_restoration(self):
        self.connection.execute.return_value.fetchall.return_value = [
            {'policy_id': 1, 'file_name': 'absent-policy.txt', 'local_pdf_path': 'absent-policy.txt'}]
        with self.assertRaises(FileNotFoundError):
            _resources(self.client, self.database, 'model')
        self.client.beta.libraries.documents.upload.assert_not_called()


class CurrentPolicyCopilotTests(unittest.TestCase):
    def test_no_current_evidence_never_reuses_old_remote_conversation(self):
        matcher=SimpleNamespace(records=[],fingerprint='current')
        with patch('app.services.semantic_matching.load_matcher',return_value=matcher), \
             patch('app.routers.policies.Mistral') as client:
            result=policy_copilot_chat(PolicyCopilotRequest(question='Explain limits',conversation_id='old-conversation'),{'user_id':'u'})
        client.assert_not_called()
        self.assertEqual(result['citations'],[])
        self.assertIsNone(result['conversation_id'])

    def run_answer(self,cited):
        rule={'id':'urn:current','policy_id':1,'rule':{'clause_id':2,'source_quote':'Exact current requirement'}}
        matcher=SimpleNamespace(records=[],fingerprint='current',clauses={2:{'section_heading':'Eligibility'}})
        with patch('app.services.semantic_matching.load_matcher',return_value=matcher), \
             patch('app.risk_knowledge.semantic_extraction.relevant_rules',return_value=[rule]), \
             patch('app.risk_knowledge.semantic_extraction.retrieval_neighborhood',return_value={}), \
             patch('app.routers.policies.MISTRAL_API_KEY','test'), \
             patch('app.routers.policies.Mistral') as client, \
             patch('app.routers.policies.observe_ai',return_value=nullcontext({})), \
             patch('app.routers.policies.shared_policy_connection') as db, \
             patch('app.routers.policies._json_object',return_value={'answer':'Supported answer','citations':[{'rule_id':cited}]}):
            db.return_value.__enter__.return_value.execute.return_value.fetchall.return_value=[{'policy_id':1,'library_policy_id':'1.1','policy_code':'POL1','title':'Policy','file_name':'source.pdf'}]
            result=policy_copilot_chat(PolicyCopilotRequest(question='Explain limits',conversation_id='old'),{'user_id':'u'})
            client.return_value.__enter__.return_value.beta.conversations.start.assert_not_called()
            return result

    def test_citations_use_exact_current_source_instead_of_model_generated_evidence(self):
        result=self.run_answer('urn:current')
        self.assertEqual(result['citations'][0]['evidence'],'Exact current requirement')
        self.assertEqual(result['knowledge_fingerprint'],'current')

    def test_unknown_rule_citation_is_rejected(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:self.run_answer('urn:old')
        self.assertEqual(error.exception.status_code,502)
