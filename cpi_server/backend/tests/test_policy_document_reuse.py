"""Fresh-catalog document ingestion must preserve deployed policy sources."""
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pypdf import PdfWriter
from app.manufacture_data import policy_generation_service as service


class PolicyDocumentReuseTests(unittest.TestCase):
    def run_job(self, directory, existing=None, invalid=False, missing=False, uploaded=False):
        spec = service.POLICY_SPECS[0]
        source = directory / f"{spec['name']}.pdf"
        if not missing:
            if invalid:
                source.write_bytes(b'not a PDF')
            else:
                writer = PdfWriter()
                writer.add_blank_page(width=612, height=792)
                writer.write(source)
        before = source.read_bytes() if source.exists() else None
        database = MagicMock()
        connection = database.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value = existing
        client = MagicMock()
        documents = client.beta.libraries.documents
        documents.list.return_value.data = [SimpleNamespace(name=source.name, id='uploaded')] if uploaded else []
        documents.upload.return_value = SimpleNamespace(id='uploaded')
        sections = [{'heading': 'Heading', 'paragraphs': ['text'] * 4}] * 10
        with ExitStack() as stack:
            stack.enter_context(patch.object(service, 'POLICY_SPECS', [spec]))
            stack.enter_context(patch.object(service, 'Mistral', return_value=MagicMock(
                __enter__=MagicMock(return_value=client))))
            stack.enter_context(patch.object(service, '_resources', return_value=('library', 'agent')))
            conversation = stack.enter_context(patch.object(service, '_start_conversation'))
            stack.enter_context(patch.object(service, '_response_text', return_value='Summary ' * 40))
            stack.enter_context(patch.object(service, '_json_object', return_value={'sections': sections}))
            def render_pdf(path, *args):
                writer = PdfWriter()
                for _ in range(10):
                    writer.add_blank_page(width=612, height=792)
                writer.write(path)
                return 10
            render = stack.enter_context(patch.object(service, '_render_pdf', side_effect=render_pdf))
            stack.enter_context(patch.object(service, '_wait_for_document'))
            stack.enter_context(patch('app.scripts.import_external_policies.import_policies', return_value=(10, 0)))
            stack.enter_context(patch('app.scripts.map_policy_relationships.map_policy_relationships'))
            service.run_policy_generation('job', database, 'key', directory, directory)
        calls = connection.execute.call_args_list
        inserts = [call for call in calls if 'INSERT INTO policy_documents' in call.args[0]]
        failed = [call for call in calls if "status = 'failed'" in call.args[0]]
        completed = [call for call in calls if "status = 'completed'" in call.args[0]]
        return source, before, documents, conversation, render, inserts, failed, completed

    def test_fresh_catalog_uploads_existing_pdf_without_regenerating(self):
        with tempfile.TemporaryDirectory() as directory:
            source, before, documents, conversation, render, inserts, failed, completed = self.run_job(Path(directory))
            self.assertEqual(source.read_bytes(), before)
            render.assert_not_called()
            documents.upload.assert_called_once()
            self.assertEqual(conversation.call_count, 1)
            self.assertEqual(conversation.call_args.kwargs['telemetry_operation'], 'policy_summary')
            self.assertEqual(len(inserts), 1)
            self.assertEqual(inserts[0].args[1][10], 1)  # actual source page count
            self.assertFalse(failed)
            self.assertTrue(completed)

    def test_existing_provider_document_is_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, documents, _, render, inserts, failed, completed = self.run_job(Path(directory), uploaded=True)
            documents.upload.assert_not_called()
            render.assert_not_called()
            self.assertEqual(len(inserts), 1)
            self.assertFalse(failed)
            self.assertTrue(completed)

    def test_invalid_existing_source_fails_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            source, before, documents, conversation, render, inserts, failed, completed = self.run_job(Path(directory), invalid=True)
            self.assertEqual(source.read_bytes(), before)
            render.assert_not_called()
            conversation.assert_not_called()
            documents.upload.assert_not_called()
            self.assertFalse(inserts)
            self.assertTrue(failed)
            self.assertFalse(completed)

    def test_missing_pdf_still_uses_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            source, _, documents, conversation, render, inserts, failed, completed = self.run_job(Path(directory), missing=True)
            render.assert_called_once()
            self.assertTrue(source.is_file())
            documents.upload.assert_called_once()
            self.assertEqual(conversation.call_count, 2)
            self.assertNotIn('telemetry_operation', conversation.call_args_list[0].kwargs)
            self.assertEqual(len(inserts), 1)
            self.assertFalse(failed)
            self.assertTrue(completed)
