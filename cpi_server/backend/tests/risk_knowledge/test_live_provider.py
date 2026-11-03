import os
import json
import httpx
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app.risk_knowledge.llm import provider_from_env,MistralLLMProvider,MockLLMProvider
from app.risk_knowledge.models import Classifications, CLASSIFICATIONS
from app.risk_knowledge.models import Concept, Provenance


class KnowledgeProviderTests(unittest.TestCase):
    def test_classification_schema_exposes_allowed_categories_and_requires_a_result(self):
        categories=Classifications.model_json_schema()['properties']['categories']
        self.assertEqual(categories['items']['enum'],CLASSIFICATIONS)
        self.assertEqual(categories['minItems'],1)
        for invalid in ([],['SCOPE','PURPOSE'],['scope']):
            with self.assertRaises(ValueError):
                Classifications(categories=invalid)

    def test_unsupported_category_retry_includes_allowed_values_and_fallback(self):
        try:Classifications(categories=['SCOPE','PURPOSE'])
        except ValueError as error:invalid=error
        expected=Classifications(categories=['SCOPE','OTHER'])
        response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=expected))])
        with patch('mistralai.client.Mistral') as client,patch('app.config.MISTRAL_API_KEY','test-key'):
            parse=client.return_value.__enter__.return_value.chat.parse
            parse.side_effect=[invalid,response]
            result=MistralLLMProvider().run('clause_classification',{'text':'Purpose and scope of this policy.'})
        self.assertEqual(result,expected)
        correction=parse.call_args.kwargs['messages'][-1]['content']
        self.assertIn('Use only these categories:',correction)
        self.assertIn('Use OTHER for purpose',correction)
        self.assertNotIn('Return null confidence',parse.call_args.kwargs['messages'][0]['content'])

    def test_unsupported_category_is_not_reported_as_truncated_json(self):
        try:Classifications(categories=['PURPOSE'])
        except ValueError as error:invalid=error
        with patch('mistralai.client.Mistral') as client,patch('app.config.MISTRAL_API_KEY','test-key'):
            parse=client.return_value.__enter__.return_value.chat.parse
            parse.side_effect=invalid
            with self.assertRaisesRegex(ValueError,'AI returned an unsupported clause category after 3 attempts'):
                MistralLLMProvider().run('clause_classification',{'text':'Purpose of this policy.'})
        self.assertEqual(parse.call_count,3)
    def test_network_timeout_is_retried_with_backoff(self):
        expected=Classifications(categories=['RULE'])
        response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=expected))])
        with patch('mistralai.client.Mistral') as client,patch('app.config.MISTRAL_API_KEY','test-key'), \
             patch('app.risk_knowledge.llm.sleep') as sleep:
            parse=client.return_value.__enter__.return_value.chat.parse
            parse.side_effect=[httpx.ReadTimeout('Model timed out'),response]
            self.assertEqual(MistralLLMProvider().run('clause_classification',{'text':'Must comply.'}),expected)
        self.assertEqual(parse.call_count,2)
        sleep.assert_called_once_with(2)

    def test_rate_limit_is_retried_but_authentication_failure_is_not(self):
        class ProviderError(Exception):
            def __init__(self,status):self.status_code=status
        expected=Classifications(categories=['RULE'])
        response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=expected))])
        with patch('mistralai.client.Mistral') as client,patch('app.config.MISTRAL_API_KEY','test-key'), \
             patch('app.risk_knowledge.llm.sleep'):
            parse=client.return_value.__enter__.return_value.chat.parse
            parse.side_effect=[ProviderError(429),response]
            self.assertEqual(MistralLLMProvider().run('clause_classification',{'text':'Must comply.'}),expected)
            parse.reset_mock()
            parse.side_effect=ProviderError(401)
            with self.assertRaises(ProviderError):
                MistralLLMProvider().run('clause_classification',{'text':'Must comply.'})
            self.assertEqual(parse.call_count,1)
    def test_truncated_json_is_retried_without_accepting_partial_output(self):
        expected=Classifications(categories=['RULE'])
        response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=expected))])
        with patch('mistralai.client.Mistral') as client,patch('app.config.MISTRAL_API_KEY','test-key'):
            parse=client.return_value.__enter__.return_value.chat.parse
            parse.side_effect=[json.JSONDecodeError('Unterminated string','{"categories":"',14),response]
            result=MistralLLMProvider().run('clause_classification',{'text':'Must comply.'})
        self.assertEqual(result,expected)
        self.assertEqual(parse.call_count,2)

    def test_repeated_truncation_has_bounded_retries_and_actionable_error(self):
        with patch('mistralai.client.Mistral') as client,patch('app.config.MISTRAL_API_KEY','test-key'):
            parse=client.return_value.__enter__.return_value.chat.parse
            parse.side_effect=json.JSONDecodeError('Unterminated string','{"items":"',10)
            with self.assertRaisesRegex(ValueError,'clause_classification: AI returned incomplete.*3 attempts'):
                MistralLLMProvider().run('clause_classification',{'text':'Must comply.'})
        self.assertEqual(parse.call_count,3)

    def test_compact_enrichment_restores_original_parent_provenance(self):
        parent=Concept(concept_id='RATING',preferred_name='Internal rating',data_type='STRING',
            metadata={'key_flag':'FK'},source=Provenance(document_id='SCHEMA',document_name='Model.xlsx',
                origin='SOURCE_SCHEMA',passage='Original schema definition',cell='A2:F2'))
        with patch('mistralai.client.Mistral') as client,patch('app.config.MISTRAL_API_KEY','test-key'):
            def parse(**kwargs):
                schema=kwargs['response_format']
                self.assertEqual(schema.model_json_schema()['properties']['items']['maxItems'],8)
                self.assertNotIn('metadata',json.loads(kwargs['messages'][1]['content'])['concepts'][0])
                output=schema(items=[{'parent_concept':'RATING','preferred_name':'Credit rating'}])
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=output))])
            client.return_value.__enter__.return_value.chat.parse.side_effect=parse
            result=MistralLLMProvider().run('taxonomy_enrichment',{'concepts':[parent.model_dump()]})
        self.assertEqual(result.items[0].source,parent.source)
        self.assertEqual(result.items[0].data_type,'STRING')
        self.assertEqual(result.items[0].metadata,{'key_flag':'FK'})
        self.assertEqual(result.items[0].status,'AI_PROPOSED')

    def test_ontology_schema_restricts_both_endpoints_to_supplied_ids(self):
        with patch('mistralai.client.Mistral') as client,patch('app.config.MISTRAL_API_KEY','test-key'):
            def parse(**kwargs):
                schema=kwargs['response_format']
                model=schema.model_json_schema()
                relation=model['$defs']['SuppliedOntologyRelationship']['properties']
                self.assertEqual(relation['subject']['enum'],['A','B'])
                self.assertEqual(relation['object']['enum'],['A','B'])
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=schema(items=[])))])
            client.return_value.__enter__.return_value.chat.parse.side_effect=parse
            result=MistralLLMProvider().run('ontology_discovery',{'concepts':[{'concept_id':'A'},{'concept_id':'B'}]})
        self.assertEqual(result.items,[])

    def test_runtime_defaults_to_mistral_and_isolated_tests_can_select_mock(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertIsInstance(provider_from_env(),MistralLLMProvider)
            self.assertIsInstance(provider_from_env(default='mock'),MockLLMProvider)

    def test_configured_model_returns_typed_task_output(self):
        expected=Classifications(categories=['RULE'])
        response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=expected))])
        with patch('mistralai.client.Mistral') as client,patch('app.config.MISTRAL_API_KEY','test-key'):
            parse=client.return_value.__enter__.return_value.chat.parse
            parse.return_value=response
            result=MistralLLMProvider().run('clause_classification',{'text':'Exposure must not exceed 100 USD.'})
        self.assertEqual(result,expected)
        self.assertIn('OTHER',parse.call_args.kwargs['messages'][0]['content'])
        self.assertEqual(parse.call_args.kwargs['response_format'],Classifications)
