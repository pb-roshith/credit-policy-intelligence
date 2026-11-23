import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,MagicMock
from fastapi.testclient import TestClient
from app.risk_knowledge.llm import MockLLMProvider
from app.risk_knowledge.service import IntelligenceService
from fastapi import FastAPI
from app.routers import risk_knowledge as main
from app.risk_knowledge.demo import SAMPLE_REQUEST


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.service=IntelligenceService(Path(cls.temp.name)/'api.sqlite3',Path(cls.temp.name)/'data',provider=MockLLMProvider())
        cls.service.bootstrap_demo()
        cls.service._catalog=([],[],[])
        app=FastAPI()
        app.include_router(main.router)
        app.dependency_overrides[main.current_user]=lambda: {'user_id':'test-reviewer','role':'credit_analyst'}
        app.dependency_overrides[main.get_service]=lambda: cls.service
        cls.app=app
        cls.client=TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None,None,None)
        cls.temp.cleanup()

    def test_state_excludes_earlier_rule_store(self):
        from types import SimpleNamespace
        matcher=SimpleNamespace(records=[],documents=[],clauses={},fingerprint='current',graph={'nodes':[],'relationships':[],'ontology_version':'1.2.0'})
        with patch('app.services.semantic_matching.load_matcher',return_value=matcher), \
             patch('app.routers.risk_knowledge.shared_policy_connection') as db:
            db.return_value.__enter__.return_value.execute.return_value.fetchall.return_value=[]
            response=self.client.get('/api/risk-knowledge/state')
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['counts']['published_rules'],0)
        self.assertEqual(data['rules'],[])
        self.assertEqual(data['pipeline'],'policy-semantic-llm-v1')
        self.assertTrue(all(c['source']['origin']=='SOURCE_SCHEMA' for c in self.client.get('/api/risk-knowledge/taxonomy').json()))

    def test_earlier_evaluation_route_is_retired(self):
        self.assertEqual(self.client.post('/api/risk-knowledge/evaluate',json=SAMPLE_REQUEST).status_code,410)

    def test_upload_process_and_download(self):
        text=b'For exposure above INR 2 million, bespoke approval shall be required.'
        upload=self.client.post('/api/risk-knowledge/assets/policy',files={'file':('New policy.txt',text,'text/plain')})
        self.assertEqual(upload.status_code,200)
        doc=upload.json()
        response=self.client.post('/api/risk-knowledge/documents/'+doc['document_id']+'/process')
        self.assertEqual(response.status_code,410)
        with patch('app.routers.risk_knowledge.audit_export') as audit:
            self.assertEqual(self.client.get('/api/risk-knowledge/documents/'+doc['document_id']+'/download').content,text)
            self.assertEqual(audit.call_args.args[2], 'risk-knowledge-document:' + doc['document_id'])

    def test_candidate_approval_gate(self):
        d=self.service.ingest('Ambiguous.txt',b'Bespoke approval is required.','policy')
        self.service.process(d['document_id'])
        rule=next(r for r in self.service.repo.all('policy_rules') if r['policy']['document_id']==d['document_id'])
        response=self.client.post('/api/risk-knowledge/review/rule/'+rule['rule_id'],json={'status':'APPROVED','reviewer':'API reviewer','notes':'Incomplete extraction'})
        self.assertEqual(response.status_code,410)

    def test_invalid_request_date(self):
        request=copy.deepcopy(SAMPLE_REQUEST)
        request['as_of']='2026-99-99'
        self.assertEqual(self.client.post('/api/risk-knowledge/evaluate',json=request).status_code,410)

    def test_graph_alias_uses_semantic_projection(self):
        with patch('app.routers.risk_knowledge.semantic_graph',return_value={'nodes':[],'edges':[]}) as graph:
            response=self.client.get('/api/risk-knowledge/graph?limit=180')
        self.assertEqual(response.status_code,200)
        graph.assert_called_once_with(focus='',limit=6)

    def test_unknown_objects_and_wrong_format(self):
        self.assertEqual(self.client.get('/api/risk-knowledge/documents/does-not-exist').status_code,404)
        self.assertEqual(self.client.post('/api/risk-knowledge/assets/policy',files={'file':('bad.exe',b'data')}).status_code,422)

    def test_malformed_archive_is_input_error(self):
        self.assertEqual(self.client.post('/api/risk-knowledge/assets/schema',files={'file':('broken.xlsx',b'not a zip')}).status_code,422)

    def test_reviewer_required(self):
        r=self.service.state()['rules'][0]
        self.assertEqual(self.client.post('/api/risk-knowledge/review/rule/'+r['rule_id'],json={'status':'REJECTED','reviewer':'','notes':''}).status_code,422)

    def test_schema_contract_and_export(self):
        schema=self.client.get('/openapi.json').json()
        self.assertIn('/api/risk-knowledge/evaluate',schema['paths'])
        with patch('app.routers.risk_knowledge.semantic_knowledge',return_value={'rules':[]}) as current, \
             patch('app.routers.risk_knowledge.audit_export') as audit:
            self.assertEqual(self.client.get('/api/risk-knowledge/export/rules').json(),{'rules':[]})
            current.assert_called_once()
            self.assertEqual(audit.call_args.args[2], 'risk-knowledge:rules')
        self.assertTrue(self.client.get('/api/risk-knowledge/request-fields').json())


if __name__=='__main__':
    unittest.main()
