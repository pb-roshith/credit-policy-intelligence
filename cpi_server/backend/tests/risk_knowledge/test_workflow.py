import copy
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
import openpyxl
from app.config import RISK_SCHEMA_DIR
from app.risk_knowledge.demo import POLICY_TEXT, TEMPLATES, SAMPLE_REQUEST
from app.risk_knowledge.graph import InMemoryGraphRepository
from app.risk_knowledge.ingestion import LABEL, parse_document, parse_schema
from app.risk_knowledge.llm import MockLLMProvider
from app.risk_knowledge.models import Rule
from app.risk_knowledge.service import IntelligenceService


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.service=IntelligenceService(Path(cls.temp.name)/'state.sqlite3',Path(cls.temp.name)/'data',provider=MockLLMProvider())
        cls.service.bootstrap_demo()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_demo_counts_come_from_stored_objects(self):
        state=self.service.state()
        self.assertEqual(state['counts']['source_documents'],len(state['documents']))
        self.assertEqual(state['counts']['approved_rules'],sum(r['status']=='APPROVED' for r in state['rules']))

    def test_every_edge_has_provenance_and_real_endpoints(self):
        graph=self.service.graph.snapshot()
        ids={n['id'] for n in graph['nodes']}
        self.assertGreater(len(graph['edges']),20)
        for e in graph['edges']:
            self.assertIn('passage',e['provenance'])
            self.assertIn(e['source'],ids)
            self.assertIn(e['target'],ids)

    def test_unknown_wording_cannot_be_auto_approved(self):
        d=self.service.ingest('Unfamiliar.txt',b'For high risk borrowers, special approval shall be required unless regional limits apply.','policy')
        self.service.process(d['document_id'])
        r=next(r for r in self.service.repo.all('policy_rules') if r['policy']['document_id']==d['document_id'])
        self.assertEqual(r['status'],'CANDIDATE')
        self.assertTrue(r['requires_review'])
        self.assertIsNone(r['confidence'])
        with self.assertRaisesRegex(ValueError,'Approval blocked'):
            self.service.review('rule',r['rule_id'],'APPROVED','Tester','Source still ambiguous')

    def test_clause_text_and_original_bytes_survive(self):
        text='## 4. Scope\n\n4.1 The borrower must obtain approval.\n'
        d=self.service.ingest('Provenance.md',text.encode(),'policy')
        clause=next(c for c in self.service.repo.all('clauses') if c['document_id']==d['document_id'] and c['source']['clause']=='4.1')
        self.assertEqual(clause['raw_text'],'4.1 The borrower must obtain approval.\n')
        self.assertEqual(clause['source']['passage'],clause['raw_text'])
        self.assertEqual((self.service.upload_dir/d['metadata']['stored_file']).read_bytes(),text.encode())
        self.assertIsNone(clause['source']['page'])

    def test_processing_is_idempotent_for_reviewed_rules(self):
        d=next(d for d in self.service.state()['documents'] if d['document_name']=='Synthetic_Credit_Standard.md')
        before=self.service.repo.all('policy_rules')
        self.service.process(d['document_id'])
        self.assertEqual(before,self.service.repo.all('policy_rules'))

    def test_no_cooccurrence_relationships(self):
        d=self.service.ingest('No triples.txt',b'Borrower, Credit Facility and Product are mentioned together.','reference')
        count=len(self.service.repo.all('ontology_relationships'))
        self.service.process(d['document_id'])
        self.assertEqual(count,len(self.service.repo.all('ontology_relationships')))

    def test_candidate_rule_approval_edit_reapproval_and_audit(self):
        candidate=next(r for r in self.service.state()['rules'] if r['rule_name']=='Board approval threshold')
        identifier=candidate['rule_id']
        self.assertEqual(candidate['status'],'CANDIDATE')
        self.service.review('rule',identifier,'APPROVED','Test reviewer','Compared every source condition')
        rule=self.service.repo.get('policy_rules',identifier)
        self.assertIn(identifier,self.service.graph.approved_rule_ids())
        self.service.edit_rule(identifier,rule,'Test reviewer','Confirming reviewed structured content')
        self.assertNotIn(identifier,self.service.graph.approved_rule_ids())
        self.assertEqual(self.service.repo.get('policy_rules',identifier)['status'],'REVIEWED')
        self.service.review('rule',identifier,'APPROVED','Test reviewer','Reapproved after complete review')
        self.assertTrue(any(a['payload'].get('action')=='EDIT' for a in self.service.repo.audit()))
        self.service.review('rule',identifier,'REJECTED','Test reviewer','End test with rule excluded')

    def test_edit_cannot_change_source(self):
        r=copy.deepcopy(next(r for r in self.service.state()['rules'] if r['status']=='APPROVED'))
        r['policy']['passage']='Altered policy wording'
        with self.assertRaisesRegex(ValueError,'immutable'):
            self.service.edit_rule(r['rule_id'],r,'Reviewer','Source substitution attempted')

    def test_empty_exception_cannot_be_approved(self):
        from app.risk_knowledge.validation import validate_rule
        r=Rule.model_validate(next(r for r in self.service.state()['rules'] if r['rule_name']=='SME financial statements'))
        r.exceptions[0].conditions=[]
        checks=validate_rule(r,self.service.taxonomy,self.service.repo.get('clauses',r.clause_id))
        self.assertFalse(checks['expression_groups_complete'])

    def test_rejection_of_taxonomy_invalidates_rules(self):
        original=self.service.repo.get('taxonomy_concepts','DEMO-rating')
        self.service.review('taxonomy','DEMO-rating','REJECTED','Reviewer','Rating scale under investigation')
        result=self.service.evaluate(SAMPLE_REQUEST)
        rule=next(r for r in result['results'] if r['rule_name'].startswith('Elevated'))
        self.assertEqual(rule['status'],'INSUFFICIENT_DATA')
        self.service.repo.put('taxonomy_concepts','DEMO-rating',original)
        self.service.refresh()

    def test_schema_exact_names_flags_and_unknown_metadata(self):
        workbook=openpyxl.Workbook()
        sheet=workbook.active
        sheet.title='Authoritative'
        sheet.append(['Unique Reference','FACT/DIM/LKP/Report','CRDM Entity','CRDM Attribute','PK/FK','Description'])
        sheet.append(['EX1','DIM','Dim_Loan','Rating','FK','Internal rating definition.'])
        sheet.append(['EX2','DIM','Dim_loan','Rating','PK','Different case is retained.'])
        scratch=workbook.create_sheet('Scratch')
        scratch.append(['Dim_Loan','Dim_loan','Not a relationship'])
        buffer=BytesIO();workbook.save(buffer)
        d,concepts=parse_schema('Schema.xlsx',buffer.getvalue())
        self.assertEqual({c.preferred_name for c in concepts if c.kind=='ENTITY'},{'Dim_Loan','Dim_loan'})
        fields=[c for c in concepts if c.kind=='ATTRIBUTE']
        self.assertTrue(all(c.status=='SOURCE' and c.data_type=='UNKNOWN' and c.allowed_values==[] for c in fields))
        self.assertEqual(fields[0].metadata['key_flag'],'FK')
        self.assertEqual(fields[0].source.cell,'A2:F2')
        self.assertIn('Not a relationship',d.raw_text)

    def test_real_workbook_record_count(self):
        path=RISK_SCHEMA_DIR / 'Risk Data Model_Oct 2026.xlsx'
        if not path.is_file():
            self.skipTest('User workbook not bundled in this checkout')
        d,concepts=parse_schema(path.name,path.read_bytes())
        self.assertEqual(d.metadata['attribute_records'],4506)
        self.assertEqual(d.metadata['entities'],197)
        self.assertEqual(sum(c.kind=='ATTRIBUTE' for c in concepts),4506)
        self.assertTrue(all(c.source.origin=='SOURCE_SCHEMA' for c in concepts))

    def test_conflict_retains_two_sources_no_winner(self):
        conflicts=[f for f in self.service.state()['conflicts'] if f['kind']=='POTENTIAL_POLICY_CONFLICT']
        self.assertTrue(conflicts)
        self.assertEqual(conflicts[0]['precedence'],'UNKNOWN')
        self.assertEqual(len(conflicts[0]['sources']),2)
        self.assertTrue(any(e['predicate']=='CONFLICTS_WITH' for e in self.service.graph.edges))

    def test_llm_boundary_validates_json(self):
        class InvalidProvider:
            name='InvalidProvider'
            def run(self,task,context):return {'unexpected':'not structured output'}
        with self.assertRaises(ValueError):
            self.service.call('clause_classification',{},InvalidProvider())

    def test_docx_reader(self):
        from zipfile import ZipFile
        buffer=BytesIO()
        with ZipFile(buffer,'w') as archive:
            archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Exact policy wording</w:t></w:r></w:p></w:body></w:document>')
        d,clauses=parse_document('test.docx',buffer.getvalue(),'policy')
        self.assertEqual(clauses[0].raw_text,'Exact policy wording')
        self.assertIsNone(clauses[0].source.page)

    def test_markdown_heading_and_numbered_clauses_without_blank_lines(self):
        text='## 4. Approvals\n4.1 Approval is required.\n4.2 Exceptions require review.'
        document,clauses=parse_document('compact.md',text.encode(),'policy')
        self.assertEqual(len(clauses),3)
        self.assertEqual(clauses[1].raw_text,'4.1 Approval is required.')
        self.assertEqual(clauses[1].source.section,'## 4. Approvals')

    def test_pdf_page_provenance(self):
        from pypdf import PdfReader
        # Minimal PDF with real content; no fabricated page metadata in the reader.
        stream=b'BT /F1 12 Tf 40 100 Td (Policy approval required.) Tj ET'
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                 b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
                 b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
        blob=b'%PDF-1.4\n';offsets=[0]
        for i,o in enumerate(objects,1):
            offsets.append(len(blob));blob+=f'{i} 0 obj\n'.encode()+o+b'\nendobj\n'
        start=len(blob);blob+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{v:010} 00000 n \n'.encode() for v in offsets[1:])+f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode()
        d,clauses=parse_document('Policy.pdf',blob,'policy')
        self.assertIn('Policy approval required.',clauses[0].raw_text)
        self.assertEqual(clauses[0].source.page,1)


if __name__=='__main__':
    unittest.main()
