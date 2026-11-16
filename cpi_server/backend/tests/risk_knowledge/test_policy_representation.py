import copy
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock,patch
from fastapi import HTTPException
from app.risk_knowledge.policy_grammar import parse_requirement,RequirementFrame,is_non_rule
from app.risk_knowledge.policy_representation import (build_representation,compile_graph,coverage_summary,
    graph_from_representation,seal,add_requirement,digest)
from app.risk_knowledge.policy_fallback import propose_unresolved
from app.risk_knowledge.representation_governance import check_definition,SourceInterpretationReview,review_span
from app.risk_knowledge.repositories import SQLiteRepository
from app.services.rule_engine import execute_rule


HIGH='For term loans, the maximum tenor is 10 years for borrowers rated BBB- or higher.'
LOW='For term loans to borrowers rated below BBB-, the maximum tenor is 5 years.'
DSCR='The minimum Debt Service Coverage Ratio (Net Operating Income/Total Debt Service) is 1.25x for all borrowers.'


def fixture(texts=(HIGH,LOW,DSCR)):
    policy={'policy_id':7,'title':'Credit limits','source_type':'uploaded'}
    version={'id':81,'version':'1','checksum':'source-checksum','effective_date':date(2026,1,1)}
    document={'id':71,'checksum':'source-checksum'}
    clauses=[{'id':91+i,'sequence':i+1,'source_excerpt':text,'clause_number':str(i+1),'page_number':i+1} for i,text in enumerate(texts)]
    return policy,version,document,clauses


def representation(texts=(HIGH,LOW,DSCR)):
    return build_representation(*fixture(texts))


class GrammarTests(unittest.TestCase):
    def test_rating_and_facility_conditions_survive_compilation_and_select_different_rules(self):
        rep=representation();rules=compile_graph(rep,rep['source_clauses'])
        high,low=rules[:2]
        self.assertEqual(high.applicability_conditions.all[1].value,'BBB-')
        self.assertEqual(high.applicability_conditions.all[1].operator,'greater_than_or_equal')
        self.assertEqual(low.applicability_conditions.all[1].operator,'less_than')
        request={'facility':'Term Loan','borrower_credit_rating':'BBB','recommended_tenor_years':8}
        self.assertEqual(execute_rule(high.model_dump(),request)['result'],'Pass')
        self.assertEqual(execute_rule(low.model_dump(),request)['result'],'Not Applicable')
        request['borrower_credit_rating']='BB'
        self.assertEqual(execute_rule(high.model_dump(),request)['result'],'Not Applicable')
        d=low.model_dump();d['severity']='BREACH'
        self.assertEqual(execute_rule(d,request)['result'],'Breach')
        request.pop('borrower_credit_rating')
        self.assertEqual(execute_rule(d,request)['result'],'Unable to Assess')

    def test_registered_formula_and_units_compile_without_model_arithmetic(self):
        rep=representation((DSCR,));rule=compile_graph(rep,rep['source_clauses'])[0]
        self.assertEqual(rule.calculation_logic.field,'dscr')
        self.assertEqual(rule.threshold_value,1.25)
        self.assertEqual(rule.threshold_unit,'x')

    def test_unknown_formula_scope_negation_and_qualifiers_are_not_erased(self):
        for text in [HIGH[:-1]+', provided that cash flows are stable.',
                     'Exposure shall not exceed 100 USD except for approved exceptions.',
                     'Exposure should not exceed 100 USD.',
                     'Exposure may not exceed 100 USD.',
                     'Exposure shall not exceed 100 USD; higher limits require approval.',
                     'The minimum DSCR (Other Operating Income/Total Debt Service) is 1.25x.',
                     'For investment-grade corporates, the maximum tenor is 10 years.',
                     'For borrowers rated below INVALID, the maximum tenor is 5 years.',
                     'The maximum tenor is 10 years for borrowers rated BBB- or higher and strong cash flows.',
                     'The maximum tenor is 10 months.']:
            with self.subTest(text=text):
                self.assertIsNone(parse_requirement(text)[0])

    def test_pdf_whitespace_is_preserved_in_source_offsets(self):
        text='\n  For term loans, the maximum tenor is 10\nyears for borrowers rated BBB- or higher.\n'
        rep=representation((text,));rule=compile_graph(rep,rep['source_clauses'])[0]
        self.assertIn('10\nyears',rule.source_excerpt)
        row=rep['coverage'][0]
        self.assertEqual(text[row['start']:row['end']],rule.source_excerpt)

    def test_unrecognized_passages_and_nonnumeric_obligations_are_not_silently_dropped(self):
        rep=representation(('The bank must obtain suitable legal advice.',
                            'Borrowers must submit audited financial statements.',
                            'For example, exposure may exceed 100 USD.'))
        self.assertEqual(coverage_summary(rep)['total_spans'],3)
        self.assertEqual(coverage_summary(rep)['unresolved_spans'],2)
        rules=compile_graph(rep,rep['source_clauses'])
        self.assertEqual(len(rules),1)
        self.assertEqual(rules[0].rule_type,'documentary')
        self.assertEqual(execute_rule(rules[0].model_dump(),{'documents':['audited_financial_statements']})['result'],'Pass')

    def test_numbered_requirements_are_not_classified_as_harmless_headings(self):
        self.assertFalse(is_non_rule('1. Borrowers must submit audited financial statements'))
        self.assertTrue(is_non_rule('1. Scope'))
        self.assertFalse(is_non_rule('Version: Exposure must not exceed 100 USD'))

    def test_inherited_facility_scope_is_not_guessed_from_an_isolated_fragment(self):
        self.assertIsNone(parse_requirement('For borrowers rated below BBB-, the maximum tenor is 5 years.')[0])
        self.assertIsNotNone(parse_requirement(HIGH[:-1]+' by a recognized credit rating agency.')[0])

    def test_ambiguous_ai_synonym_is_not_used_as_a_taxonomy_binding(self):
        concept={'kind':'ATTRIBUTE','concept_id':'wrong','preferred_name':'Other Operating Income','status':'APPROVED',
                 'source':{'origin':'SOURCE_SCHEMA','document_name':'Workbook','passage':'Income'}}
        rep=build_representation(*fixture((DSCR,)),concepts=[concept])
        self.assertFalse(any(e['predicate']=='MAPS_TO' for e in rep['edges']))


class GraphCompilerTests(unittest.TestCase):
    def test_repeatability_and_exact_spreadsheet_mapping(self):
        concept={'kind':'ATTRIBUTE','concept_id':'DSCR','preferred_name':'Debt Service Coverage Ratio','status':'SOURCE',
                 'metadata':{'source_entity':'Fact_Customer_Financial_Statements'},
                 'source':{'origin':'SOURCE_SCHEMA','document_name':'Workbook','passage':'Ratio of cash available','cell':'A62:I62'}}
        args=fixture((DSCR,))
        a=build_representation(*args,concepts=[concept]);b=build_representation(*args,concepts=[concept])
        self.assertEqual(a,b)
        self.assertTrue(any(e['predicate']=='MAPS_TO' and e['target']=='DSCR' for e in a['edges']))
        self.assertEqual([r.model_dump() for r in compile_graph(a,args[3])],[r.model_dump() for r in compile_graph(b,args[3])])

    def test_changed_source_and_modified_graph_cannot_compile(self):
        rep=representation();changed=copy.deepcopy(rep['source_clauses']);changed[0]['source_excerpt']=HIGH.replace('10','20')
        with self.assertRaisesRegex(ValueError,'source changed'):compile_graph(rep,changed)
        rep['nodes'][-1]['payload']={'field':'wrong'}
        with self.assertRaisesRegex(ValueError,'integrity'):compile_graph(rep,rep['source_clauses'])

    def test_resealed_graph_cannot_drop_rating_condition_or_invent_threshold(self):
        for mode in ('scope','threshold','metric','direction','predicate'):
            rep=representation((HIGH,))
            if mode=='scope':rep['edges']=[e for e in rep['edges'] if e['predicate']!='HAS_SCOPE']
            elif mode=='threshold':next(n for n in rep['nodes'] if n['type']=='PolicyConstraint')['payload']['threshold']=20
            elif mode=='metric':next(n for n in rep['nodes'] if n['type']=='PolicyMetric')['payload']['field']='invented_field'
            elif mode=='direction':
                e=next(e for e in rep['edges'] if e['predicate']=='USES_METRIC');e['source'],e['target']=e['target'],e['source']
            else:rep['edges'][0]['predicate']='MAKES_UP_REQUIREMENT'
            seal(rep)
            with self.subTest(mode=mode),self.assertRaises(ValueError):compile_graph(rep,rep['source_clauses'])

    def test_unreviewed_fallback_never_compiles_even_with_exact_quote(self):
        rep=representation(('A bespoke tenor limit applies.',));sid=rep['coverage'][0]['span_id']
        rid=add_requirement(rep,sid,RequirementFrame(metric='tenor',operator='less_than_or_equal',threshold=100,unit='years'),'LLM_FALLBACK','PROPOSED')
        rep['coverage'][0].update(requirement_ids=[rid],status='LLM_PROPOSED')
        seal(rep)
        self.assertEqual(compile_graph(rep,rep['source_clauses']),[])
        self.assertFalse(coverage_summary(rep)['complete'])

    def test_coverage_cannot_drop_a_passage_or_a_requirement_even_after_resealing(self):
        for mode in ('passage','requirement','false_nonrule'):
            rep=representation((HIGH,))
            if mode=='passage':rep['coverage']=[]
            elif mode=='requirement':rep['coverage'][0]['requirement_ids']=[]
            else:rep['coverage'][0].update(status='NON_RULE',requirement_ids=[])
            seal(rep)
            with self.subTest(mode=mode),self.assertRaises(ValueError):compile_graph(rep,rep['source_clauses'])

    def test_equal_labels_in_wrong_source_entity_do_not_create_semantic_bindings(self):
        concept={'kind':'ATTRIBUTE','concept_id':'bureau-tenor','preferred_name':'Tenor','status':'APPROVED',
                 'metadata':{'source_entity':'Fact_Bureau_Credit_Instrument'},
                 'source':{'origin':'SOURCE_SCHEMA','document_name':'Workbook','passage':'Historical bureau tenor'}}
        rep=build_representation(*fixture((HIGH,)),concepts=[concept])
        self.assertFalse(any(e['predicate']=='MAPS_TO' for e in rep['edges']))

    def test_forged_approval_and_changed_inventory_semantics_are_rejected(self):
        rep=representation((HIGH,));rule=compile_graph(rep,rep['source_clauses'])[0].model_dump(mode='json')
        row={'definition':rule}
        self.assertTrue(check_definition(row,rep,rep['source_clauses']))
        row['definition']['applicability_conditions']=None
        with self.assertRaises(HTTPException):check_definition(row,rep,rep['source_clauses'])

    def test_reviewed_exclusion_has_three_valued_execution(self):
        rep=representation(('Bespoke exposure requirements: 100 USD, excluding Excluded Sector.',));sid=rep['coverage'][0]['span_id']
        frame=RequirementFrame(metric='exposure',operator='less_than_or_equal',threshold=100,unit='USD',
                               exclusions={'field':'industry','operator':'equals','value':'Excluded Sector'})
        approval={'reviewer':'analyst','source_checksum':rep['source_checksum'],'frame_digest':digest(frame.model_dump(mode='json'))}
        rid=add_requirement(rep,sid,frame,'SOURCE_REVIEW','APPROVED',approval=approval)
        rep['coverage'][0].update(requirement_ids=[rid],status='REVIEWED');seal(rep)
        rule=compile_graph(rep,rep['source_clauses'])[0]
        self.assertEqual(execute_rule(rule.model_dump(),{'industry':'Excluded Sector'})['result'],'Not Applicable')
        self.assertEqual(execute_rule(rule.model_dump(),{'exposure':10,'currency':'USD'})['result'],'Unable to Assess')


class LastResortTests(unittest.TestCase):
    def test_supported_spans_are_never_sent_to_fallback_and_proposals_remain_unresolved(self):
        rep=representation((HIGH,'A bespoke tenor limit of 8 years applies.'))
        def provider(sources):
            self.assertEqual(len(sources),1);self.assertNotIn(HIGH,str(sources))
            return {'interpretations':[{'span_id':sources[0]['span_id'],'source_quote':sources[0]['source_quote'],
                    'frames':[{'metric':'tenor','operator':'less_than_or_equal','threshold':8,'unit':'years'}]}]}
        propose_unresolved(rep,provider)
        self.assertEqual(rep['fallback']['attempted'],1)
        self.assertEqual(len(compile_graph(rep,rep['source_clauses'])),1)
        self.assertEqual(coverage_summary(rep)['unresolved_spans'],1)
        with patch('app.risk_knowledge.policy_fallback.llm_provider',side_effect=AssertionError('Retry must not recall unchanged span')) as again:
            propose_unresolved(rep,again)
        again.assert_not_called()

    def test_no_model_for_fully_recognized_policy(self):
        rep=representation()
        model=MagicMock(side_effect=AssertionError('No fallback needed'))
        propose_unresolved(rep,model);model.assert_not_called()

    def test_bad_quotes_duplicates_and_provider_failures_do_not_erase_deterministic_rules(self):
        for mode in ('quote','duplicate','outage'):
            rep=representation((HIGH,'A bespoke tenor limit applies.'))
            def provider(sources):
                if mode=='outage':raise RuntimeError('Provider unavailable')
                frame={'metric':'tenor','operator':'less_than_or_equal','threshold':8,'unit':'years'}
                return {'interpretations':[{'span_id':sources[0]['span_id'],'source_quote':'invented' if mode=='quote' else sources[0]['source_quote'],
                                            'frames':[frame,frame] if mode=='duplicate' else [frame]}]}
            propose_unresolved(rep,provider)
            self.assertTrue(rep['fallback']['failures'])
            self.assertEqual(len(compile_graph(rep,rep['source_clauses'])),1)

    def test_ontology_rejects_unknown_fields_metrics_documents_and_units(self):
        for value in [{'metric':'invented','threshold':10,'unit':'x'},
                      {'metric':'tenor','threshold':10,'unit':'USD'},
                      {'document':'invented_document','threshold':True},
                      {'metric':'tenor','threshold':10,'unit':'years','scope':{'field':'invented_attribute','operator':'equals','value':'X'}}]:
            with self.subTest(value=value),self.assertRaises(ValueError):RequirementFrame.model_validate(value)

    def test_reviewer_cannot_supply_an_absent_limit_or_change_a_literal_rating(self):
        from app.risk_knowledge.policy_grammar import validate_frame_source
        frame=RequirementFrame(metric='tenor',operator='less_than_or_equal',threshold=11,unit='years')
        with self.assertRaisesRegex(ValueError,'Threshold'):validate_frame_source(frame,HIGH)
        frame=RequirementFrame(metric='tenor',operator='less_than_or_equal',threshold=10,unit='years',
                               scope={'field':'borrower_credit_rating','operator':'greater_than_or_equal','value':'BBB'})
        with self.assertRaisesRegex(ValueError,'Scope value'):validate_frame_source(frame,HIGH)

    def test_only_source_reviewers_can_approve_fallback(self):
        rep=representation(('Bespoke rules apply.',))
        body=SourceInterpretationReview(representation_id=rep['id'],content_digest=rep['content_digest'],span_id=rep['coverage'][0]['span_id'],disposition='NON_RULE',notes='Reviewed complete passage')
        with self.assertRaises(HTTPException) as error:review_span(7,body,{'user_id':'rm','role':'relationship_manager'})
        self.assertEqual(error.exception.status_code,403)


class OperationalPipelineTests(unittest.TestCase):
    def test_conditional_writes_preserve_a_concurrent_review(self):
        with TemporaryDirectory() as tmp:
            repo=SQLiteRepository(Path(tmp)/'test.sqlite3')
            initial={'content_digest':'initial','value':'grammar'}
            self.assertTrue(repo.compare_and_put('metadata','representation',initial,None))
            reviewed={'content_digest':'reviewed','value':'human source interpretation'}
            self.assertTrue(repo.compare_and_put('metadata','representation',reviewed,'initial'))
            fallback={'content_digest':'fallback','value':'late model response'}
            self.assertFalse(repo.compare_and_put('metadata','representation',fallback,'initial'))
            self.assertEqual(repo.get('metadata','representation'),reviewed)

    def test_graph_is_durable_before_rule_storage_and_no_llm_for_supported_source(self):
        from app.risk_knowledge.graph_first import process_policy
        with TemporaryDirectory() as tmp:
            repo=SQLiteRepository(Path(tmp)/'test.sqlite3')
            # A source taxonomy row prevents optional workbook initialization in this unit fixture.
            repo.put('taxonomy_concepts','term',{'concept_id':'term','kind':'ATTRIBUTE','preferred_name':'Tenor','status':'SOURCE','source':{'origin':'SOURCE_SCHEMA','document_name':'Workbook','passage':'Tenor'}})
            connection=MagicMock()
            def execute(query,params=None):
                cursor=MagicMock()
                cursor.fetchone.return_value=(None if 'FROM policy_rule_versions' in query else {'payload':repo.get('metadata',params[0])} if 'FROM risk_knowledge_objects' in query else {'checksum':'source-checksum','is_current':True})
                return cursor
            connection.__enter__.return_value.execute.side_effect=execute
            def store(payload,user,**kwargs):
                d=payload.definition.model_dump(mode='json')
                self.assertIsNotNone(repo.get('metadata',d['representation_id']))
                self.assertEqual(kwargs['force_draft'],True)
                return {'id':101,'definition':d,'status':'Draft'}
            with patch('app.services.rule_extraction.ingest_policy',return_value=fixture(('Exposure shall not exceed 100 USD.',))), \
                 patch('app.services.rule_extraction.shared_policy_connection',return_value=connection), \
                 patch('app.risk_knowledge.graph_first.PostgreSQLRepository',return_value=repo), \
                 patch('app.services.rule_governance.store_rule',side_effect=store), \
                 patch('app.risk_knowledge.graph_first.llm_provider',side_effect=AssertionError('No model should run')):
                result=process_policy(7,{'user_id':'analyst'},fallback_provider=False)
            self.assertTrue(result['coverage']['complete'])
            self.assertEqual(result['rules_proposed'],1)
            self.assertEqual(result['rules_approved'],0)
            self.assertEqual(result['llm_fallback_spans'],0)


if __name__=='__main__':unittest.main()
