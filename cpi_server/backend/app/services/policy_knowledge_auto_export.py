"""Coalesce shared knowledge changes into portable files outside HTTP requests."""
import json
import logging
import os
from pathlib import Path
import threading

from .policy_knowledge_package import (
    PACKAGE_DIR, database_fingerprint, export_package, shared_policy_connection,
)

logger = logging.getLogger(__name__)


class KnowledgeAutoExporter:
    def __init__(self, directory=PACKAGE_DIR, interval=None, connection_factory=None, exporter=None):
        self.directory = Path(directory)
        self.interval = max(1, float(interval if interval is not None else os.getenv('POLICY_KNOWLEDGE_EXPORT_INTERVAL_SECONDS', '15')))
        self.connection_factory = connection_factory or shared_policy_connection
        self.exporter = exporter or export_package
        self.stopped = threading.Event()
        self.thread = None
        self.last_fingerprint = None
        self.last_error = None
        self.last_counts = None
        source = self.directory / 'knowledge.json'
        if source.is_file():
            try:
                from .policy_knowledge_package import checksum, encoded
                envelope = json.loads(source.read_text(encoding='utf-8'))
                if checksum((encoded(envelope['payload']) + '\n').encode()) == envelope['sha256']:
                    self.last_fingerprint = envelope['payload'].get('database_fingerprint')
            except (ValueError, KeyError, OSError):
                # An invalid/missing prior package is replaced from the database.
                pass

    def tick(self):
        """Export a committed snapshot once; retain the previous file on failure."""
        try:
            with self.connection_factory() as c:
                c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                if not c.execute("SELECT 1 FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND payload->>'kind'='semantic_policy' LIMIT 1").fetchone():
                    return False
                fingerprint = database_fingerprint(c)
            if fingerprint == self.last_fingerprint and (self.directory / 'knowledge.json').is_file():
                return False
            result = self.exporter(self.directory, self.connection_factory)
            # Use the export snapshot's fingerprint: a concurrent edit will be
            # picked up on the next tick, rather than marked saved accidentally.
            self.last_fingerprint = result['database_fingerprint']
            self.last_counts = result
            self.last_error = None
            logger.info('Automatically updated policy knowledge package: %s', result)
            return True
        except Exception as error:
            message = f'{type(error).__name__}: {error}'
            if message != self.last_error:
                logger.exception('Automatic policy knowledge export failed; previous package retained; retrying in %s seconds', self.interval)
            self.last_error = message
            return False

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stopped.clear()
        def run():
            while not self.stopped.is_set():
                self.tick()
                self.stopped.wait(self.interval)
            # Flush edits made during the last polling interval on clean shutdown.
            self.tick()
        self.thread = threading.Thread(target=run, name='policy-knowledge-auto-export', daemon=True)
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=10)


def create_auto_exporter():
    if os.getenv('POLICY_KNOWLEDGE_AUTO_EXPORT', 'true').lower() not in ('true', '1', 'yes'):
        return None
    return KnowledgeAutoExporter(directory=os.getenv('POLICY_KNOWLEDGE_EXPORT_DIR') or PACKAGE_DIR)
