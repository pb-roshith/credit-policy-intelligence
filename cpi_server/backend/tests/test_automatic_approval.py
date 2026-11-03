import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from app.risk_knowledge.service import IntelligenceService
from app.risk_knowledge.models import Concept,Relationship,Provenance
from app.services.automatic_approval import approve_knowledge


class AutomaticKnowledgeApprovalTests(unittest.TestCase):
    def test_approves_concepts_before_relationships_and_preserves_rejections(self):
        with TemporaryDirectory() as directory:
            service=IntelligenceService(Path(directory)/'state.sqlite3',Path(directory)/'archive')
            source=Provenance(document_id='source',document_name='Source schema',origin='SOURCE_SCHEMA',passage='Source fields')
            for identifier,status in [('A','SOURCE'),('B','AI_PROPOSED'),('C','REJECTED')]:
                item=Concept(concept_id=identifier,preferred_name=identifier,status=status,source=source)
                service.repo.put('taxonomy_concepts',identifier,item.model_dump())
            for identifier,target in [('accepted','B'),('unapproved-endpoint','C')]:
                item=Relationship(relationship_id=identifier,subject='A',predicate='HAS',object=target,source=source)
                service.repo.put('ontology_relationships',identifier,item.model_dump())
            result=approve_knowledge(service)
            self.assertEqual(result,{'taxonomy_concepts':2,'ontology_relationships':1})
            self.assertEqual(service.repo.get('ontology_relationships','accepted')['status'],'APPROVED')
            self.assertEqual(service.repo.get('taxonomy_concepts','C')['status'],'REJECTED')
            self.assertEqual(service.repo.get('ontology_relationships','unapproved-endpoint')['status'],'AI_PROPOSED')
            self.assertEqual(approve_knowledge(service),{'taxonomy_concepts':0,'ontology_relationships':0})
