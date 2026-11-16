import copy
from datetime import date
import unittest
from unittest.mock import MagicMock,patch
from fastapi import HTTPException
from app.risk_knowledge.policy_representation import build_representation,compile_graph,seal,frame_from_graph,graph_from_representation,digest
from app.risk_knowledge.rule_identity import semantic_digest,publish_drafts
from app.risk_knowledge.representation_governance import check_definition
from app.risk_knowledge.rule_readiness import (dependency_state,dependency_snapshot,inspect_rule,effective_rule,
    RuleApproval,approve_rule,scopes_disjoint)
from app.services.rule_engine import execute_rule

LIMIT='For term loans, the maximum tenor is 10 years for borrowers rated BBB- or higher.'
REPORT='Monthly reports must be sent to the risk committee.'


def fixture(context=REPORT,status='Draft'):
    clauses=[{'id':1,'sequence':1,'source_excerpt':LIMIT},{'id':2,'sequence':2,'source_excerpt':context}]
    rep=build_representation({'policy_id':6,'title':'Credit policy'},{'id':21,'version':'1','effective_date':date(2026,1,1)}, {'checksum':'source'},clauses)
    definition=compile_graph(rep,clauses)[0].model_dump(mode='json')
    row={'id':10,'rule_key':'family','version':2,'status':status,'active':status=='Active','policy_id':6,'clause_id':1,
         'policy_version_id':21,'policy_version':'1','policy_fingerprint':'fp','effective_from':date(2026,1,1),
         'effective_to':None,'definition':definition,'created_by':'system:graph-compiler','extraction_key':'graph-first:test'}
    return row,rep,clauses


def reviewed(row,rep,disposition='covered'):
    state=dependency_snapshot(row,rep)
    return {'kind':'rule_dependency_review','rule_key':row['rule_key'],'source_checksum':rep['source_checksum'],
            'snapshot_digest':state['digest'],'reviewer':'analyst',
            'resolutions':[{'dependency_id':i['id'],'disposition':disposition,'rationale':'Checked against the source and structured scope'} for i in state['items']]}


class RuleSpecificReadinessTests(unittest.TestCase):
    def test_unrelated_unresolved_reporting_does_not_block_rule_approval(self):
        row,rep,clauses=fixture()
        row['definition'].update(severity='BREACH',data_source='Verified loan record')
        result=inspect_rule(row,rep,clauses)
        self.assertFalse(result['coverage']['complete'])
        self.assertEqual(result['coverage']['unresolved_spans'],1)
        self.assertTrue(result['can_approve'])
        self.assertFalse(result['requires_whole_policy_resolution'])

    def test_scope_and_exception_dependencies_cannot_be_silently_ignored(self):
        for context in ['Scope\nThis policy applies to term loans.', 'Exceptions\nA bespoke exception may override these limits.']:
            with self.subTest(context=context):
                row,rep,_=fixture(context)
                self.assertFalse(dependency_state(row,rep)['ready'])
                self.assertEqual(len(dependency_state(row,rep)['items']),1)
                self.assertTrue(dependency_state(row,rep,reviewed(row,rep))['ready'])
                self.assertFalse(dependency_state(row,rep,reviewed(row,rep,'needs_work'))['ready'])

    def test_relevant_source_change_invalidates_dependency_clearance(self):
        row,rep,_=fixture('Exceptions\nApproved deviations require a source review.')
        review=reviewed(row,rep)
        changed=copy.deepcopy(rep);changed['source_clauses'][1]['source_excerpt']+=' A stricter limit also applies.'
        self.assertFalse(dependency_state(row,changed,review)['ready'])

    def test_unrelated_review_does_not_invalidate_rule_or_dependencies(self):
        row,rep,clauses=fixture('Scope\nThis policy applies to term loans.')
        review=reviewed(row,rep)
        rep['reviews'].append({'span_id':'unrelated','notes':'Source bookkeeping only'})
        seal(rep)
        self.assertTrue(check_definition(row,rep,clauses))
        self.assertTrue(dependency_state(row,rep,review)['ready'])

    def test_changed_rule_condition_is_still_rejected(self):
        row,rep,clauses=fixture()
        row['definition']['applicability_conditions']=None
        with self.assertRaises(HTTPException):check_definition(row,rep,clauses)

    def test_disjointness_requires_a_proof_for_every_alternative(self):
        a={'field':'property_type','operator':'equals','value':'Investment Property'}
        b={'any':[{'field':'property_type','operator':'equals','value':'Primary Residence'},a]}
        self.assertFalse(scopes_disjoint(a,b))
        self.assertTrue(scopes_disjoint(a,{'field':'property_type','operator':'equals','value':'Vacation Home'}))
        self.assertFalse(scopes_disjoint(a,{'field':'property_type','operator':'not_equals','value':'Investment Property'}))

    def test_dependency_guards_are_used_and_missing_facts_are_unknown(self):
        row,_,_=fixture()
        review={'resolutions':[{'conditions':{'field':'is_secured','operator':'equals','value':True},
                                'exclusions':{'field':'ltv_exception_applies','operator':'equals','value':True}}]}
        effective=effective_rule(row,review)
        request={'facility':'Term Loan','borrower_credit_rating':'BBB','recommended_tenor_years':8}
        self.assertEqual(execute_rule(effective['definition'],request)['result'],'Unable to Assess')
        request.update(is_secured=True,ltv_exception_applies=False)
        self.assertEqual(execute_rule(effective['definition'],request)['result'],'Pass')
        request['ltv_exception_applies']=True
        self.assertEqual(execute_rule(effective['definition'],request)['result'],'Not Applicable')
        self.assertIsNone(row['definition'].get('applicability_exclusions'))


class StablePublicationTests(unittest.TestCase):
    def test_recompilation_preserves_existing_approval_and_governance_fields(self):
        row,rep,_=fixture(status='Approved')
        row['definition'].update(severity='BREACH',data_source='Bank system',representation_digest='older whole-document digest')
        definitions=compile_graph(rep,rep['source_clauses'])
        connection=MagicMock();connection.execute.return_value.fetchone.return_value=row
        with patch('app.services.rule_governance.store_rule') as store:
            results,changed=publish_drafts(rep,definitions,{'user_id':'analyst'},connection)
        store.assert_not_called()
        self.assertEqual(changed,0);self.assertEqual(results[0]['id'],row['id'])
        self.assertEqual(results[0]['status'],'Approved')
        self.assertEqual(results[0]['definition']['data_source'],'Bank system')

    def test_whole_document_fingerprint_is_not_rule_meaning(self):
        row,_,_=fixture()
        changed=copy.deepcopy(row['definition']);changed['representation_digest']='new audit digest'
        changed['extraction_confidence']=0;changed['extraction_notes']='New review notes'
        self.assertEqual(semantic_digest(changed),semantic_digest(row['definition']))
        changed['threshold_value']=11
        self.assertNotEqual(semantic_digest(changed),semantic_digest(row['definition']))

    def test_changed_rule_creates_one_revision_in_the_same_family(self):
        row,rep,_=fixture(status='Approved')
        definition=compile_graph(rep,rep['source_clauses'])[0]
        row['definition']['threshold_value']=9
        connection=MagicMock();connection.execute.return_value.fetchone.return_value=row
        with patch('app.services.rule_governance.store_rule',return_value={'id':11,'status':'Draft'}) as store:
            result,changed=publish_drafts(rep,[definition],{'user_id':'analyst'},connection)
        self.assertEqual(changed,1);self.assertEqual(store.call_args.kwargs['previous'],10)
        self.assertEqual(row['status'],'Approved')


class FakeConnection:
    def __init__(self,row,rep,clauses):
        self.row=copy.deepcopy(row);self.rep=copy.deepcopy(rep);self.clauses=clauses;self.metadata={};self.writes=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,query,params=None):
        cursor=MagicMock();cursor.fetchone.return_value=None;cursor.fetchall.return_value=[]
        if query.startswith('SELECT rule_key,definition FROM policy_rule_versions'):cursor.fetchone.return_value={'rule_key':self.row['rule_key'],'definition':self.row['definition']}
        elif 'SELECT payload FROM risk_knowledge_objects' in query:
            value=self.rep if params[0]==self.rep['id'] else self.metadata.get(params[0])
            cursor.fetchone.return_value={'payload':copy.deepcopy(value)} if value else None
        elif query.startswith('SELECT * FROM policy_rule_versions WHERE id='):cursor.fetchone.return_value=copy.deepcopy(self.row)
        elif query.startswith('SELECT id FROM policy_rule_versions WHERE rule_key'):cursor.fetchone.return_value={'id':self.row['id']}
        elif 'SELECT checksum,is_current FROM policy_versions' in query:cursor.fetchone.return_value={'checksum':self.rep['source_checksum'],'is_current':True}
        elif 'SELECT id,source_excerpt FROM policy_clauses' in query:cursor.fetchall.return_value=self.clauses
        elif 'AS policy_status' in query:cursor.fetchone.return_value={'is_current':True,'version':'1','policy_status':'Active','fingerprint':'fp'}
        elif 'INSERT INTO risk_knowledge_objects' in query:
            self.metadata[params[0]]=copy.deepcopy(params[1].obj);self.writes.append(query)
        elif 'UPDATE policy_rule_versions SET definition=' in query:
            self.row.update(definition=copy.deepcopy(params[0].obj),status='Approved',active=False,approved_by=params[1])
            cursor.fetchone.return_value=copy.deepcopy(self.row);self.writes.append(query)
        return cursor


class UnifiedApprovalTests(unittest.TestCase):
    def setup_case(self,context=REPORT):
        row,rep,clauses=fixture(context)
        connection=FakeConnection(row,rep,clauses)
        ready=inspect_rule(row,rep,clauses)
        body={'review_token':ready['review_token'],'dependency_digest':ready['dependencies']['digest'],
              'resolutions':reviewed(row,rep)['resolutions'],'severity':'BREACH','data_source':'Verified bank loan record',
              'comment':'Checked rule, source and relevant context','confirmed':True}
        return connection,RuleApproval.model_validate(body)

    def test_one_action_approves_independent_rule_without_global_coverage_completion(self):
        connection,body=self.setup_case()
        with patch('app.database.shared_policy_connection',return_value=connection), \
             patch('app.services.rule_governance.children'),patch('app.services.rule_governance.audit'):
            result=approve_rule(10,body,{'user_id':'analyst','role':'credit_analyst'})
        self.assertEqual(result['rule']['status'],'Approved')
        self.assertFalse(result['policy_coverage_complete'])
        self.assertEqual(result['rule']['definition']['data_source'],'Verified bank loan record')

    def test_relevant_dependency_must_have_an_explicit_decision(self):
        connection,body=self.setup_case('Exceptions\nA bespoke exception may override these limits.')
        body.resolutions=[]
        with patch('app.database.shared_policy_connection',return_value=connection),self.assertRaises(HTTPException) as caught:
            approve_rule(10,body,{'user_id':'analyst','role':'admin'})
        self.assertEqual(caught.exception.status_code,422);self.assertFalse(connection.writes)

    def test_reapproval_creates_revision_and_preserves_approved_definition(self):
        connection,body=self.setup_case()
        connection.row['status']='Approved'
        original=copy.deepcopy(connection.row)
        body.review_token=inspect_rule(connection.row,connection.rep,connection.clauses)['review_token']
        def create_revision(payload,user,previous,**kwargs):
            self.assertEqual(previous,original['id'])
            self.assertEqual(connection.row,original)
            connection.row={**original,'id':11,'version':3,'status':'Draft',
                            'definition':payload.definition.model_dump(mode='json')}
            return copy.deepcopy(connection.row)
        with patch('app.database.shared_policy_connection',return_value=connection), \
             patch('app.services.rule_governance.store_rule',side_effect=create_revision), \
             patch('app.services.rule_governance.children'),patch('app.services.rule_governance.audit'):
            result=approve_rule(10,body,{'user_id':'analyst','role':'credit_analyst'})
        self.assertEqual(result['rule']['id'],11)
        self.assertEqual(result['rule']['status'],'Approved')
        self.assertIsNone(original['definition']['data_source'])
        self.assertEqual(result['dependency_review']['rule_version_id'],11)

    def test_stale_review_token_cannot_approve(self):
        connection,body=self.setup_case();body.review_token='stale'
        with patch('app.database.shared_policy_connection',return_value=connection),self.assertRaises(HTTPException) as caught:
            approve_rule(10,body,{'user_id':'analyst','role':'admin'})
        self.assertEqual(caught.exception.status_code,409);self.assertFalse(connection.writes)

    def test_reader_cannot_approve(self):
        _,body=self.setup_case()
        with self.assertRaises(HTTPException) as caught:approve_rule(10,body,{'user_id':'rm','role':'relationship_manager'})
        self.assertEqual(caught.exception.status_code,403)


if __name__=='__main__':unittest.main()
