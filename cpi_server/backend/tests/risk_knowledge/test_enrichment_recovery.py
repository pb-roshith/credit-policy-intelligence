import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.risk_knowledge.llm import MockLLMProvider
from app.risk_knowledge.models import Concept, ConceptCandidates, Provenance
from app.risk_knowledge.service import IntelligenceService


class EnrichmentRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service=IntelligenceService(Path(self.temp.name)/'state.sqlite3',Path(self.temp.name)/'data',
                                         provider=MockLLMProvider())
        for number in range(9):
            concept=Concept(concept_id=f'R{number}',preferred_name=f'Rating {number}',
                source=Provenance(document_id='SCHEMA',document_name='Schema.xlsx',origin='SOURCE_SCHEMA',
                                  passage=f'Rating definition {number}'))
            self.service.repo.put('taxonomy_concepts',concept.concept_id,concept.model_dump())

    def test_completed_batches_are_reused_after_failure_and_approval_changes(self):
        call=Mock(side_effect=[ConceptCandidates(items=[]),ValueError('Incomplete JSON')])
        self.service.call=call
        with self.assertRaisesRegex(ValueError,'Incomplete JSON'):
            self.service.enrich(reuse_completed=True)
        self.assertEqual([len(args.args[1]['concepts']) for args in call.call_args_list],[4,4])
        for concept in self.service.repo.all('taxonomy_concepts'):
            self.service.repo.put('taxonomy_concepts',concept['concept_id'],concept|{'status':'APPROVED'})
        call.reset_mock(side_effect=True)
        call.return_value=ConceptCandidates(items=[])
        self.service.enrich(reuse_completed=True)
        self.assertEqual([len(args.args[1]['concepts']) for args in call.call_args_list],[4,1])
        call.reset_mock()
        self.service.enrich(reuse_completed=True)
        call.assert_not_called()
        concept=self.service.repo.get('taxonomy_concepts','R0')
        self.service.repo.put('taxonomy_concepts','R0',concept|{'description':'Changed source definition'})
        self.service.enrich(reuse_completed=True)
        self.assertEqual(call.call_count,1)

    def test_empty_schema_does_not_call_ai(self):
        for concept in self.service.repo.all('taxonomy_concepts'):
            self.service.repo.put('taxonomy_concepts',concept['concept_id'],concept|{'kind':'ENTITY'})
        self.service.call=Mock()
        self.assertEqual(self.service.enrich(),{'created':0})
        self.service.call.assert_not_called()
