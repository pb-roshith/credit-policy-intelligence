import copy
import json
import unittest
from unittest.mock import patch,MagicMock
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from app.routers.decision import router
from app.security import current_user
from app.schemas import ScenarioRunRequest
from app.services.scenario_requests import request_baseline,available_requests
from app.services.scenario_simulator import calculate_metrics

USER={'user_id':'owner','role':'credit_analyst'}
INPUTS={'facility_amount':0.5,'collateral_coverage':110,'risk_rating':'BB+','pricing_bps':275,'tenor_years':1.5,'covenants':'Full'}


class RequestScenarioTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI();app.include_router(router);app.dependency_overrides[current_user]=lambda:USER
        self.client=TestClient(app)
        self.baseline={'credit_request_number':'deal_AbC','currency':'INR','inputs':INPUTS,'request_facts':{'borrower_name':'Example borrower'},'assumptions':[]}

    def test_request_id_is_required_and_opaque_deal_case_is_preserved(self):
        self.assertEqual(self.client.post('/api/decision-scenarios',json={'scenario_name':'Downside',**INPUTS}).status_code,422)
        request=ScenarioRunRequest(credit_request_number=' deal_AbC ',scenario_name=' Downside ',**INPUTS)
        self.assertEqual(request.credit_request_number,'deal_AbC')
        self.assertEqual(request.scenario_name,'Downside')
        self.assertEqual(self.client.get('/api/decision-scenarios').status_code,422)

    def test_save_binds_request_snapshot_and_model_changes_to_selected_request(self):
        connection=MagicMock();connection.execute.return_value.fetchone.return_value=None
        stored={}
        def persist(operation):
            db=MagicMock()
            def execute(sql,params):
                stored['sql']=sql;stored['params']=params
                cursor=MagicMock();cursor.fetchone.return_value={'scenario_id':9,'scenario_name':'Downside','created_at':'2026-11-12'}
                return cursor
            db.execute.side_effect=execute
            return operation(db)
        with patch('app.routers.decision.request_baseline',return_value=self.baseline) as baseline, \
             patch('app.routers.decision.db_connection') as database, \
             patch('app.routers.decision.run_db_transaction',side_effect=persist), \
             patch('app.routers.decision.ScenarioRecommendationAgent') as agent:
            database.return_value.__enter__.return_value=connection
            agent.return_value.run.return_value=('mock-agent',['First','Second','Third'])
            response=self.client.post('/api/decision-scenarios',json={'credit_request_number':'deal_AbC','scenario_name':'Downside',**INPUTS,'facility_amount':0.6,'currency':'INR'})
        self.assertEqual(response.status_code,201,response.text)
        result=response.json();self.assertEqual(result['credit_request_number'],'deal_AbC')
        self.assertEqual(result['request_snapshot']['inputs']['facility_amount'],0.5)
        self.assertEqual(result['results']['scenario_changes']['facility_amount'],{'baseline':0.5,'scenario':0.6})
        self.assertEqual(result['inputs']['currency'],'INR')
        self.assertEqual(stored['params'][1],'deal_AbC')
        self.assertEqual(json.loads(stored['params'][2]),self.baseline)
        baseline.assert_called_once_with('deal_AbC',USER)
        self.assertEqual(connection.execute.call_args.args[1],('deal_AbC','Downside'))
        self.assertEqual(agent.return_value.run.call_args.kwargs['request_context'],self.baseline)

    def test_request_access_is_checked_before_scenario_or_ai_access(self):
        with patch('app.routers.decision.request_baseline',side_effect=HTTPException(404,'Unavailable')), \
             patch('app.routers.decision.ScenarioRecommendationAgent') as agent, \
             patch('app.routers.decision.db_connection') as database:
            response=self.client.post('/api/decision-scenarios',json={'credit_request_number':'other-owner','scenario_name':'Downside',**INPUTS})
        self.assertEqual(response.status_code,404);agent.assert_not_called();database.assert_not_called()

    def test_list_and_detail_cannot_load_another_requests_scenarios(self):
        with patch('app.routers.decision.request_baseline',return_value=self.baseline),patch('app.routers.decision.db_connection') as database:
            db=database.return_value.__enter__.return_value
            db.execute.return_value.fetchall.return_value=[]
            self.assertEqual(self.client.get('/api/decision-scenarios?credit_request_number=deal_AbC').status_code,200)
            self.assertIn('WHERE credit_request_number=%s',db.execute.call_args.args[0])
            self.assertEqual(db.execute.call_args.args[1],('deal_AbC',))
            db.execute.return_value.fetchone.return_value={'credit_request_number':'different-request'}
            self.assertEqual(self.client.get('/api/decision-scenarios/7?credit_request_number=deal_AbC').status_code,404)
            self.assertEqual(db.execute.call_args.args[1],(7,'deal_AbC'))

    def test_same_name_conflicts_only_within_selected_request(self):
        with patch('app.routers.decision.request_baseline',return_value=self.baseline),patch('app.routers.decision.db_connection') as database, \
             patch('app.routers.decision.ScenarioRecommendationAgent') as agent:
            database.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'exists':True}
            response=self.client.post('/api/decision-scenarios',json={'credit_request_number':'deal_AbC','scenario_name':'Downside',**INPUTS})
        self.assertEqual(response.status_code,409);agent.assert_not_called()

    def test_currency_change_requires_reset_instead_of_silent_fx_conversion(self):
        with patch('app.routers.decision.request_baseline',return_value=self.baseline),patch('app.routers.decision.ScenarioRecommendationAgent') as agent:
            response=self.client.post('/api/decision-scenarios',json={'credit_request_number':'deal_AbC','scenario_name':'Downside',**INPUTS,'currency':'USD'})
        self.assertEqual(response.status_code,409);agent.assert_not_called()

    def test_linking_legacy_scenario_preserves_original_results_and_records_manual_association(self):
        original={'scenario_id':4,'scenario_name':'Earlier','created_at':'before','inputs':{**INPUTS,'currency':'INR'},'results':{'expected_loss':1},'recommendations':['One','Two','Three']}
        params=[]
        def transaction(operation):
            db=MagicMock()
            def execute(sql,args):
                cursor=MagicMock()
                if sql.startswith('UPDATE'):
                    params.extend(args);cursor.fetchone.return_value={**original,'credit_request_number':args[0],'request_snapshot':json.loads(args[1])}
                else:cursor.fetchone.return_value=original
                return cursor
            db.execute.side_effect=execute;return operation(db)
        with patch('app.routers.decision.request_baseline',return_value=self.baseline),patch('app.routers.decision.run_db_transaction',side_effect=transaction):
            response=self.client.post('/api/decision-scenarios/4/link',json={'credit_request_number':'deal_AbC'})
        self.assertEqual(response.status_code,200,response.text)
        result=response.json();self.assertEqual(result['results'],original['results'])
        self.assertEqual(result['inputs'],original['inputs']);self.assertTrue(result['request_snapshot']['original_inputs_not_request_derived'])


class SimulatorBaselineTests(unittest.TestCase):
    def test_baseline_uses_server_request_amount_currency_and_fractional_tenor(self):
        proposal={'requested_amount':500000,'currency':'INR','rating':'BB+','tenure':18,'collateral_coverage':110,
                  'pricing':'SOFR + 275 bps','covenants':'Full','borrower_name':'Example'}
        before=copy.deepcopy(proposal)
        with patch('app.services.scenario_requests.assessment_request_context',return_value=('deal_AbC',proposal)):
            result=request_baseline('deal_AbC',USER)
        self.assertEqual(result['inputs'],INPUTS);self.assertEqual(result['currency'],'INR');self.assertEqual(proposal,before)

    def test_native_request_needs_no_compliance_review(self):
        with patch('app.services.scenario_requests.db_connection') as database,patch('app.services.credit_data.load_record',return_value=None), \
             patch('app.services.scenario_requests.assessment_request_context') as assessment:
            database.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={
                'requested_amount':500000,'rating':'BBB','collateral_coverage':100,'recommended_pricing_bps':275,'recommended_tenor_years':3}
            result=request_baseline('cr-1',USER)
        self.assertEqual(result['credit_request_number'],'CR-1');self.assertEqual(result['currency'],'USD')
        assessment.assert_not_called()

    def test_unknown_rating_requires_a_scenario_choice_and_preserves_source_rating(self):
        with patch('app.services.scenario_requests.assessment_request_context',return_value=('deal_AbC',{'rating':'A','requested_amount':5e6,'currency':'USD'})):
            result=request_baseline('deal_AbC',USER)
        self.assertIsNone(result['inputs']['risk_rating']);self.assertEqual(result['request_facts']['rating'],'A')
        self.assertIn('risk_rating',result['missing_fields'])

    def test_sensitivity_supports_retail_amounts_and_fractional_years(self):
        result=calculate_metrics({**INPUTS,'currency':'INR'})
        self.assertEqual(result['assumptions']['currency'],'INR')
        self.assertIn(0.5,[p['facility_amount'] for p in result['sensitivity']])
        self.assertGreater(result['expected_loss'],0)
        self.assertNotEqual(result['ecl_impact'],calculate_metrics({**INPUTS,'tenor_years':1})['ecl_impact'])


class AvailableSimulatorRequestsTests(unittest.TestCase):
    def test_candidates_use_authoritative_sources_and_distinguish_manager_accounts(self):
        native=[{'credit_request_number':'CR-1','borrower_name':'Example','facility':'Term Loan','user_id':owner,'shared_deal_id':None}
                for owner in ('manager_a','manager_b')]
        native.append({'credit_request_number':'CR-2','borrower_name':'Linked','facility':'Home loan','user_id':'manager_a','shared_deal_id':'deal_AbC'})
        with patch('app.services.scenario_requests.db_connection') as db,patch('app.services.deal_retrieval.DealRetrievalAgent.run',return_value={
            'deals':[{'id':'deal_AbC','customer':'Shared','facility':'Home loan'}]}):
            db.return_value.__enter__.return_value.execute.return_value.fetchall.return_value=native
            result=available_requests(USER)
        self.assertEqual({r['credit_request_number'] for r in result['requests']},{'CR-1@manager_a','CR-1@manager_b','deal_AbC'})
        self.assertEqual(result['notices'],[])

    def test_remote_source_failure_still_lists_accessible_stored_requests(self):
        with patch('app.services.scenario_requests.db_connection') as db,patch('app.services.deal_retrieval.DealRetrievalAgent.run',side_effect=HTTPException(503,'Offline')):
            db.return_value.__enter__.return_value.execute.return_value.fetchall.return_value=[{
                'credit_request_number':'CR-1','borrower_name':'Example','facility':'Term Loan','user_id':'owner','shared_deal_id':None}]
            result=available_requests({'user_id':'owner','role':'relationship_manager'})
        self.assertEqual(result['requests'][0]['credit_request_number'],'CR-1')
        self.assertTrue(result['notices'])

    def test_simulator_exposes_available_requests_without_loading_an_invalid_saved_selection(self):
        app=FastAPI();app.include_router(router);app.dependency_overrides[current_user]=lambda:USER
        expected={'requests':[{'credit_request_number':'CR-1@manager_a','borrower_name':'Example','facility':'Term Loan'}],'notices':[]}
        with patch('app.routers.decision.available_requests',return_value=expected),patch('app.routers.decision.request_baseline') as baseline:
            response=TestClient(app).get('/api/decision-scenarios/requests')
        self.assertEqual(response.status_code,200);self.assertEqual(response.json(),expected)
        baseline.assert_not_called()
