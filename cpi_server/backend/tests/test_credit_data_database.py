"""Rollback-only PostgreSQL verification of ownership and frozen assessments."""
import os
import unittest
from contextlib import contextmanager, ExitStack
from datetime import date
from unittest.mock import patch
import psycopg
from psycopg.rows import dict_row
from app.config import DATABASE_URL
from app.services.credit_data import synthetic_record, store_record, load_record, resolve_actual
from app.services.rule_assessment import run_rule_assessment, active_rule_candidates


@unittest.skipUnless(os.getenv('RUN_CREDIT_DATA_DB_TESTS')=='1','Enable explicit PostgreSQL credit data tests')
class CreditDataDatabaseTests(unittest.TestCase):
    def setUp(self):
        # Read the shared catalog before opening the account fixture transaction:
        # concurrent application bootstrap may need locks on both schemas.
        self.rules=active_rule_candidates(date.today())
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        self.c=psycopg.connect(DATABASE_URL,row_factory=dict_row)
        self.stack.callback(self.c.close); self.stack.callback(self.c.rollback)
        self.c.execute('SET LOCAL search_path TO "user"')
        self.proposal=self.c.execute('SELECT * FROM credit_requests WHERE shared_deal_id IS NULL ORDER BY credit_request_number LIMIT 1').fetchone()
        if not self.proposal: self.skipTest('No demonstration request available')
        self.owner=self.proposal['user_id']
        self.c.execute("SELECT set_config('app.user_id',%s,true)",(self.owner,))
        self.c.execute('SET LOCAL ROLE credit_user_runtime')
        @contextmanager
        def connection(): yield self.c
        self.stack.enter_context(patch('app.database.db_connection',connection))
        self.stack.enter_context(patch('app.services.credit_data.load_record',wraps=load_record))
        # The governed rule comes directly from the database, unchanged.
        self.rule=next(r for r in self.rules if (r['definition'].get('calculation_logic') or {}).get('field')=='revolving_credit_tenor')

    def test_frozen_assessment_uses_persisted_actual_provenance(self):
        record=synthetic_record(dict(self.proposal),[self.rule],as_of=date.today())
        # Select the revolver tenor rule explicitly without changing its approved definition.
        record['entities']['facility'][0]['attributes']['maturity_date']['value']=str(date(date.today().year+3,date.today().month,1))
        record['entities']['facility'][0]['attributes']['maturity_date']['provenance']['value']=record['entities']['facility'][0]['attributes']['maturity_date']['value']
        store_record(record)
        self.proposal={**self.proposal,'_canonical_record':load_record(record['request_id']),'currency':'USD','evidence':[]}
        report={'decisions':[{'candidate_id':str(self.rule['id']),'candidate_type':'Rule','applicability':'Applicable'}],'policy_mappings':[]}
        with patch('app.services.rule_assessment.assessment_request_context',return_value=(record['request_id'],self.proposal)), \
             patch('app.services.rule_assessment.active_rule_candidates',return_value=[self.rule]), \
             patch('app.services.policy_scope.policy_first_applicability',return_value=report), \
             patch('app.services.rule_explanation.explain_findings',side_effect=lambda findings:[f.update(explanation='Frozen deterministic result') for f in findings]), \
             patch('app.services.rule_assessment.run_db_transaction',side_effect=lambda operation:operation(self.c)):
            result=run_rule_assessment(record['request_id'],self.owner,user={'user_id':self.owner})
        finding=result['findings'][0]
        self.assertEqual(finding['result'],'Pass')
        self.assertEqual(finding['actual'],'3.0')
        derived=next(p for p in finding['actual_data_resolution']['provenance'] if p['source_type']=='DERIVED')
        self.assertEqual(derived['inputs'][0]['source_type'],'SYNTHETIC')
        saved=self.c.execute('SELECT review FROM ai_compliance_reviews WHERE review_id=%s',(result['review_id'],)).fetchone()['review']
        record['entities']['facility'][0]['attributes']['maturity_date']['value']=str(date(date.today().year+9,date.today().month,1))
        record['entities']['facility'][0]['attributes']['maturity_date']['provenance']['value']=record['entities']['facility'][0]['attributes']['maturity_date']['value']
        store_record(record)
        self.assertEqual(saved['findings'][0]['actual'],'3.0')
        self.assertEqual(resolve_actual(self.rule,load_record(record['request_id']))['actual_value'],9)

    def test_account_isolation_and_revision(self):
        record=synthetic_record(dict(self.proposal),[self.rule],as_of=date.today())
        store_record(record); loaded=load_record(record['request_id'])
        with self.assertRaises(ValueError): store_record(record,loaded['revision']-1)
        self.c.execute("SELECT set_config('app.user_id',%s,true)",('different_credit_data_test_owner',))
        self.assertIsNone(load_record(record['request_id']))
