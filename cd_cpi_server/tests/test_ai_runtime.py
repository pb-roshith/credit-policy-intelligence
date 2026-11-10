"""Exercise the provider boundary without sending financial records externally."""
import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from pydantic import BaseModel
from ai_runtime import AIClient, GeminiClient, GeminiUnavailableError, Result


class Answer(BaseModel):
    answer: str


class GeminiRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = patch.dict(os.environ, {
            'AI_PROVIDER': 'gemini', 'GEMINI_API_KEY': 'test-key',
            'GEMINI_MODEL': 'gemini-3.5-flash-lite',
            'GEMINI_STORE_PATH': str(Path(self.directory.name) / 'store.sqlite3'),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.sdk_patch = patch('google.genai.Client')
        self.sdk = self.sdk_patch.start().return_value
        self.addCleanup(self.sdk_patch.stop)
        self.sdk.models.generate_content.return_value = Result(
            text='{"answer":"grounded"}', function_calls=[],
            usage_metadata=Result(prompt_token_count=10, candidates_token_count=5, total_token_count=15))

    def test_gemini_uses_configured_model_and_preserves_typed_contract(self):
        with AIClient(api_key='unused-mistral-key', timeout_ms=1234) as client:
            response = client.chat.parse(model='mistral-large-latest', messages=[
                {'role': 'system', 'content': 'Use only evidence'},
                {'role': 'user', 'content': 'Explain'}], response_format=Answer, temperature=0)
        args = self.sdk.models.generate_content.call_args.kwargs
        self.assertEqual(args['model'], 'gemini-3.5-flash-lite')
        self.assertTrue(args['config'].system_instruction.startswith('Use only evidence'))
        self.assertIn('"answer"', args['config'].system_instruction)
        self.assertEqual(args['config'].response_mime_type, 'application/json')
        self.assertEqual(response.choices[0].message.parsed.answer, 'grounded')
        self.assertEqual(response.usage.total_tokens, 15)
        self.sdk.close.assert_called_once()

    def test_documents_and_agents_survive_client_recreation(self):
        client = AIClient()
        library = client.beta.libraries.create(name='Borrower A')
        doc = client.beta.libraries.documents.upload(library_id=library.id,
            file={'file_name': 'evidence.txt', 'content': b'Leverage must be below 4.'})
        agent = client.beta.agents.create(instructions='Use only sources', tools=[
            {'type': 'document_library', 'library_ids': [library.id]}])
        replacement = AIClient()
        self.assertEqual(replacement.files.text_content(document_id=doc.id, library_id=library.id).text,
                         'Leverage must be below 4.')
        response = asyncio.run(replacement.beta.conversations.start_async(agent_id=agent.id,
            inputs='What is the leverage limit?', store=True))
        args = self.sdk.models.generate_content.call_args.kwargs
        contents = '\n'.join(part.text or '' for item in args['contents'] for part in item.parts)
        self.assertIn('evidence.txt', contents)
        self.assertIn('Leverage must be below 4.', contents)
        self.assertEqual(response.outputs[0].type, 'message.output')
        self.assertTrue(response.conversation_id.startswith('gemini-conversation-'))

    def test_wrong_library_cannot_read_another_document(self):
        from mistralai.client.errors import SDKError
        client = AIClient()
        first = client.beta.libraries.create(name='A')
        second = client.beta.libraries.create(name='B')
        doc = client.files.upload(library_id=first.id, file={'file_name': 'a.txt', 'content': b'private'})
        with self.assertRaises(SDKError) as caught:
            client.files.text_content(library_id=second.id, document_id=doc.id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_legacy_agent_and_library_ids_are_missing_for_gemini(self):
        from mistralai.client.errors import SDKError
        client = AIClient()
        with self.assertRaises(SDKError):
            client.beta.agents.get(agent_id='old-mistral-agent')
        agent = client.beta.agents.create(tools=[{'type': 'document_library', 'library_ids': ['old-library']}])
        with self.assertRaises(SDKError):
            client.beta.conversations.start(agent_id=agent.id, inputs='Answer')
        self.sdk.models.generate_content.assert_not_called()

    def test_function_calls_retain_the_server_tool_contract(self):
        self.sdk.models.generate_content.return_value = Result(text='',
            function_calls=[Result(name='list_owned_deals', args={}, id='call-1')], usage_metadata=None)
        client = AIClient()
        agent = client.beta.agents.create(tools=[{'type': 'function', 'function': {
            'name': 'list_owned_deals', 'description': 'Authorized records only',
            'parameters': {'type': 'object', 'properties': {}}}}])
        response = client.beta.conversations.start(agent_id=agent.id, inputs='List deals')
        call = next(item for item in response.outputs if item.type == 'function.call')
        self.assertEqual(call.name, 'list_owned_deals')
        self.assertEqual(call.arguments, '{}')
        self.assertEqual(call.tool_call_id, 'call-1')

    def test_mistral_selection_uses_original_sdk(self):
        with patch.dict(os.environ, {'AI_PROVIDER': 'mistral'}), patch('mistralai.client.Mistral') as factory:
            client = AIClient(api_key='mistral-key', timeout_ms=500)
            self.assertIs(client, factory.return_value)
            factory.assert_called_once_with(api_key='mistral-key', timeout_ms=500)

    def test_empty_and_invalid_structured_responses_fail(self):
        client = AIClient()
        self.sdk.models.generate_content.return_value.text = ''
        with self.assertRaisesRegex(ValueError, 'no usable content'):
            client.chat.complete(messages=[{'role': 'user', 'content': 'Hi'}])
        self.sdk.models.generate_content.return_value.text = '{"wrong": 1}'
        with self.assertRaises(ValueError):
            client.chat.parse(messages=[{'role': 'user', 'content': 'Hi'}], response_format=Answer)

    def test_moderation_rejects_missing_categories_and_wrong_result_count(self):
        client = AIClient()
        for content in ['[]', '{"results":[]}', '{"results":[{"categories":{}}]}']:
            self.sdk.models.generate_content.return_value.text = content
            with self.assertRaises(ValueError):
                asyncio.run(client.classifiers.moderate_async(inputs=['Synthetic input']))


class GeminiRetryTests(unittest.TestCase):
    def run_request(self, statuses):
        """Use the real SDK against an in-memory HTTP server, without delays."""
        import httpx
        from google import genai
        real_client = genai.Client
        attempts = []

        def respond(request):
            status = statuses[min(len(attempts), len(statuses) - 1)]
            attempts.append(status)
            if status != 200:
                return httpx.Response(status, json={'error': {
                    'code': status, 'message': 'Synthetic provider failure',
                    'status': 'UNAVAILABLE' if status == 503 else 'INVALID_ARGUMENT'}})
            return httpx.Response(200, json={
                'candidates': [{'content': {'role': 'model', 'parts': [{'text': 'OK'}]}, 'finishReason': 'STOP'}],
                'usageMetadata': {'promptTokenCount': 1, 'candidatesTokenCount': 1, 'totalTokenCount': 2}})

        with tempfile.TemporaryDirectory() as directory, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            def create(**kwargs):
                options = kwargs['http_options']
                self.assertEqual(options.retry_options.attempts, 6)
                self.assertEqual(options.retry_options.initial_delay, 2)
                self.assertEqual(options.retry_options.max_delay, 16)
                self.assertIn(503, options.retry_options.http_status_codes)
                # Exercise the actual retry code without making tests sleep.
                options.retry_options.initial_delay = 0
                options.retry_options.max_delay = 0
                options.retry_options.jitter = 0
                options.httpx_client = http
                return real_client(**kwargs)

            with patch.dict(os.environ, {'AI_PROVIDER': 'gemini', 'GEMINI_API_KEY': 'test-key',
                    'GEMINI_STORE_PATH': str(Path(directory) / 'store.sqlite3')}), \
                    patch('google.genai.Client', side_effect=create):
                try:
                    with AIClient() as client:
                        response = client.chat.complete(messages=[{'role': 'user', 'content': 'Hi'}])
                    return attempts, response
                except Exception as error:
                    return attempts, error

    def test_temporary_503_recovers_using_native_sdk_retries(self):
        attempts, result = self.run_request([503, 503, 200])
        self.assertEqual(attempts, [503, 503, 200])
        self.assertEqual(result.choices[0].message.content, 'OK')

    def test_persistent_503_has_bounded_attempts_and_clear_error(self):
        attempts, error = self.run_request([503])
        self.assertEqual(len(attempts), 6)
        self.assertIsInstance(error, GeminiUnavailableError)
        self.assertIn('temporarily unavailable after automatic retries', str(error))

    def test_invalid_request_is_not_retried(self):
        from google.genai.errors import ClientError
        attempts, error = self.run_request([400])
        self.assertEqual(attempts, [400])
        self.assertIsInstance(error, ClientError)


if __name__ == '__main__':
    unittest.main()
