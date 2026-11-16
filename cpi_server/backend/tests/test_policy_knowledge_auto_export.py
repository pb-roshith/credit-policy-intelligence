from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from app.services import policy_knowledge_auto_export as automatic
from app.services.policy_knowledge_package import checksum, encoded


class AutoExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.connection = MagicMock()
        self.connection.execute.return_value.fetchone.return_value = {'exists': 1}
        @contextmanager
        def factory():
            yield self.connection
        self.factory = factory
        self.export = MagicMock(side_effect=self.write_export)
        self.fingerprint = 'initial'
        self.digest_patch = patch.object(automatic, 'database_fingerprint', side_effect=lambda c: self.fingerprint)
        self.digest_patch.start()
        self.addCleanup(self.digest_patch.stop)
        self.worker = automatic.KnowledgeAutoExporter(self.directory, interval=1, connection_factory=self.factory, exporter=self.export)

    def write_export(self, directory, factory):
        payload = {'database_fingerprint': self.fingerprint}
        envelope = {'payload': payload, 'sha256': checksum((encoded(payload) + '\n').encode())}
        (directory / 'knowledge.json').write_text(json.dumps(envelope), encoding='utf-8')
        return {'database_fingerprint': self.fingerprint, 'rules': 1}

    def test_initial_export_changes_and_unchanged_ticks(self):
        self.assertTrue(self.worker.tick())
        self.assertFalse(self.worker.tick())
        self.fingerprint = 'saved-rule-change'
        self.assertTrue(self.worker.tick())
        self.assertEqual(self.export.call_count, 2)
        self.assertEqual(self.worker.last_fingerprint, 'saved-rule-change')

    def test_failure_preserves_file_and_retries_without_advancing_fingerprint(self):
        self.worker.tick()
        before = (self.directory / 'knowledge.json').read_bytes()
        self.fingerprint = 'reviewed'
        self.export.side_effect = OSError('read-only deployment folder')
        with self.assertLogs(automatic.logger, level='ERROR'):
            self.assertFalse(self.worker.tick())
        self.assertEqual((self.directory / 'knowledge.json').read_bytes(), before)
        self.assertEqual(self.worker.last_fingerprint, 'initial')
        self.export.side_effect = self.write_export
        self.assertTrue(self.worker.tick())
        self.assertIsNone(self.worker.last_error)

    def test_restart_does_not_export_unchanged_package(self):
        self.worker.tick()
        restarted = automatic.KnowledgeAutoExporter(self.directory, connection_factory=self.factory, exporter=self.export)
        self.assertFalse(restarted.tick())
        self.assertEqual(self.export.call_count, 1)

    def test_edits_during_export_are_detected_next_tick(self):
        def export_older_snapshot(directory, factory):
            self.write_export(directory, factory)
            self.fingerprint = 'newer-commit'
            return {'database_fingerprint': 'initial'}
        self.export.side_effect = export_older_snapshot
        self.assertTrue(self.worker.tick())
        self.export.side_effect = self.write_export
        self.assertTrue(self.worker.tick())
        self.assertEqual(self.worker.last_fingerprint, 'newer-commit')

    def test_deleted_package_is_recreated(self):
        self.worker.tick()
        (self.directory / 'knowledge.json').unlink()
        self.assertTrue(self.worker.tick())

    def test_no_knowledge_does_not_replace_package(self):
        self.connection.execute.return_value.fetchone.return_value = None
        self.assertFalse(self.worker.tick())
        self.export.assert_not_called()

    def test_background_worker_stops_and_flushes(self):
        exported = threading.Event()
        def export(directory, factory):
            result = self.write_export(directory, factory)
            exported.set()
            return result
        self.export.side_effect = export
        self.worker.start()
        self.addCleanup(self.worker.stop)
        self.assertTrue(exported.wait(5))
        self.fingerprint = 'last-edit-before-shutdown'
        self.worker.stop()
        self.assertFalse(self.worker.thread.is_alive())
        self.assertEqual(self.worker.last_fingerprint, 'last-edit-before-shutdown')

    def test_disabled_configuration(self):
        with patch.dict('os.environ', {'POLICY_KNOWLEDGE_AUTO_EXPORT': 'false'}):
            self.assertIsNone(automatic.create_auto_exporter())
