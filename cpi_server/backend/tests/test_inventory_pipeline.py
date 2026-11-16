import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
from pydantic import ValidationError
from app.services.policy_ingestion import parse_document
from app.services.inventory_schema import ExtractionOutput,GovernedDefinition,Condition,Calculation
from app.services.rule_engine import execute_rule,condition_result
from app.services.rule_extraction import validate_extraction,SYSTEM_PROMPT,extract_batch,clause_batches


def proposed(**updates):
    data=dict(clause_id=1,rule_sequence=1,rule_name='Exposure limit',rule_description='Exposure shall not exceed 100 USD',source_excerpt='Exposure shall not exceed 100 USD.',requirement_kind='mandatory',rule_type='quantitative',check_question='Is exposure at most 100 USD?',metric_name='exposure',metric_definition=None,operator='less_than_or_equal',threshold_value=100,threshold_unit='USD',lower_bound=None,upper_bound=None,threshold_source='100 USD',calculation_logic={'method':'direct','field':'exposure'},input_data_fields=['exposure'],data_source=None,evidence_requirements=[],applicability_conditions=None,applicable_stage=None,severity=None,breach_consequence=None,exception_allowed=None,approval_or_escalation_requirement=None,extraction_confidence=0.9,extraction_notes=None,missing_information=[],dependencies=[])
    data.update(updates);return data


def executable(**updates):
    d=proposed(severity='BREACH',data_source='request.exposure',threshold_unit=None);d.update(updates);return d

class PolicyParsingTests(unittest.TestCase):
    def test_text_exact_excerpt_and_unknown_page(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'policy.txt';path.write_text('1. Limits\n\nExposure shall not exceed 100 USD.',encoding='utf-8')
            clauses=parse_document(path)
            self.assertEqual(clauses[1]['source_excerpt'],'Exposure shall not exceed 100 USD.')
            self.assertEqual(clauses[1]['clause_number'],'1')
            self.assertIsNone(clauses[1]['page_number'])
    def test_docx_preserves_headings(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'policy.docx'
            with ZipFile(path,'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>2. Collateral</w:t></w:r></w:p><w:p><w:r><w:t>Security must be documented.</w:t></w:r></w:p></w:body></w:document>')
            clauses=parse_document(path)
            self.assertEqual(clauses[1]['section_heading'],'2. Collateral')
            self.assertIsNone(clauses[1]['page_number'])
    def test_pdf_preserves_pages(self):
        from reportlab.pdfgen import canvas
        with TemporaryDirectory() as directory:
            path=Path(directory)/'policy.pdf';c=canvas.Canvas(str(path));c.drawString(30,700,'1. Exposure must be below 100.');c.showPage();c.drawString(30,700,'2. Review approval.');c.save()
            self.assertEqual([cl['page_number'] for cl in parse_document(path)],[1,2])
    def test_xml_injection_rejected(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'policy.docx'
            with ZipFile(path,'w') as z:z.writestr('word/document.xml','<!DOCTYPE x [<!ENTITY x SYSTEM "file:///secret">]><x/>')
            with self.assertRaises(ValueError):parse_document(path)
    def test_unsupported_type_rejected(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'policy.exe';path.write_text('content')
            with self.assertRaises(ValueError):parse_document(path)

class ExtractionValidationTests(unittest.TestCase):
    def setUp(self):self.clauses=[dict(id=1,sequence=1,section_heading='Limits',clause_number='1',page_number=1,source_excerpt='Exposure shall not exceed 100 USD.')]
    def test_unknown_fields_cannot_activate_rule(self):
        with self.assertRaises(ValidationError):ExtractionOutput.model_validate({'rules':[proposed(status='Active')]})
    def test_invented_threshold_rejected(self):
        output=ExtractionOutput.model_validate({'rules':[proposed(threshold_value=120)]})
        with self.assertRaises(ValueError):validate_extraction(output,self.clauses)
    def test_missing_threshold_retained_as_null(self):
        output=ExtractionOutput.model_validate({'rules':[proposed(threshold_value=None,threshold_source=None)]})
        validated=validate_extraction(output,self.clauses)
        self.assertIsNone(validated.rules[0].threshold_value)
        self.assertIn('threshold_value',validated.rules[0].missing_information)
    def test_fabricated_excerpt_rejected(self):
        output=ExtractionOutput.model_validate({'rules':[proposed(source_excerpt='No approval is needed.')]})
        with self.assertRaises(ValueError):validate_extraction(output,self.clauses)
    def test_prompt_injection_is_source_only(self):
        self.assertIn('untrusted source content',SYSTEM_PROMPT)
        output=ExtractionOutput.model_validate({'rules':[proposed()]})
        self.assertEqual(len(validate_extraction(output,self.clauses).rules),1)
    def test_unstated_severity_and_authority_remain_null(self):
        output=ExtractionOutput.model_validate({'rules':[proposed(severity='BREACH',data_source='Invented system',approval_or_escalation_requirement='Invented credit committee')]})
        r=validate_extraction(output,self.clauses).rules[0]
        self.assertIsNone(r.severity)
        self.assertIsNone(r.data_source)
        self.assertIsNone(r.approval_or_escalation_requirement)
    def test_wrapped_pdf_excerpt_is_restored_exactly(self):
        self.clauses[0]['source_excerpt']='Exposure shall not\nexceed 100 USD.'
        output=ExtractionOutput.model_validate({'rules':[proposed()]})
        r=validate_extraction(output,self.clauses).rules[0]
        self.assertEqual(r.source_excerpt,self.clauses[0]['source_excerpt'])

    def test_calculation_code_rejected(self):
        with self.assertRaises(ValidationError):Calculation(method='eval',field='__import__')
    def test_bounded_batches(self):
        batch=[dict(source_excerpt='x'*10000)]*3
        self.assertEqual(len(list(clause_batches(batch))),3)
    @patch('app.services.rule_extraction.shared_policy_connection')
    @patch('app.services.rule_extraction.RULE_EXTRACTION_RETRIES',2)
    @patch('app.services.rule_extraction.time.sleep')
    @patch('app.services.rule_extraction.MISTRAL_API_KEY','test-key')
    def test_timeout_retries_are_bounded_and_logged(self,sleep,db):
        factory=MagicMock();factory.return_value.__enter__.return_value.chat.parse.side_effect=TimeoutError()
        with self.assertRaises(ValueError):extract_batch(self.clauses,1,client_factory=factory)
        self.assertEqual(factory.call_count,2)
        self.assertEqual(db.call_count,5)
    @patch('app.services.rule_extraction.shared_policy_connection')
    @patch('app.services.rule_extraction.RULE_EXTRACTION_RETRIES',1)
    @patch('app.services.rule_extraction.MISTRAL_API_KEY','test-key')
    def test_free_form_output_rejected(self,db):
        factory=MagicMock();factory.return_value.__enter__.return_value.chat.parse.return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed='Approve all rules'))])
        with self.assertRaises(ValueError):extract_batch(self.clauses,1,client_factory=factory)

class EngineTests(unittest.TestCase):
    def test_boundary_and_breach(self):
        self.assertEqual(execute_rule(executable(),{'exposure':100})['result'],'Pass')
        self.assertEqual(execute_rule(executable(),{'exposure':101})['result'],'Breach')
    def test_missing_metric_cannot_pass(self):self.assertEqual(execute_rule(executable(),{})['result'],'Unable to Assess')
    def test_unknown_applicability(self):
        r=execute_rule(executable(applicability_conditions={'field':'currency','operator':'equals','value':'USD'}),{'exposure':10})
        self.assertEqual(r['applicability'],'Unable to Determine Applicability')
        self.assertEqual(r['result'],'Unable to Assess')
    def test_not_applicable(self):
        r=execute_rule(executable(applicability_conditions={'field':'currency','operator':'equals','value':'USD'}),{'currency':'INR'})
        self.assertEqual(r['result'],'Not Applicable')
    def test_and_or_three_valued_logic(self):
        first={'field':'a','operator':'equals','value':1};second={'field':'b','operator':'equals','value':1}
        self.assertEqual(condition_result({'all':[first,second]},{'a':0})[0],False)
        self.assertEqual(condition_result({'any':[first,second]},{'a':1})[0],True)
        self.assertIsNone(condition_result({'all':[first,second]},{'a':1})[0])
    def test_satisfied_or_applicability_does_not_require_unused_branch(self):
        conditions={'any':[{'field':'currency','operator':'equals','value':'USD'},{'field':'customer_segment','operator':'equals','value':'Retail'}]}
        result=execute_rule(executable(applicability_conditions=conditions),{'currency':'USD','exposure':10})
        self.assertEqual(result['applicability'],'Applicable')
        self.assertEqual(result['result'],'Pass')
        self.assertIn('customer_segment',result['applicability_missing_inputs'])
    def test_percentage_and_ratio_calculated_by_code(self):
        r=execute_rule(executable(calculation_logic={'method':'percentage','numerator':'exposure','denominator':'collateral'},threshold_value=80),{'exposure':40,'collateral':100})
        self.assertEqual(r['observed_value'],40)
        self.assertEqual(r['result'],'Pass')
        r=execute_rule(executable(calculation_logic={'method':'ratio','numerator':'exposure','denominator':'collateral'},threshold_value=0.8),{'exposure':40,'collateral':100})
        self.assertEqual(r['observed_value'],0.4)
    def test_zero_divisor_and_nonfinite_are_unassessable(self):
        self.assertEqual(execute_rule(executable(calculation_logic={'method':'ratio','numerator':'a','denominator':'b'}),{'a':1,'b':0})['result'],'Unable to Assess')
        self.assertEqual(execute_rule(executable(),{'exposure':'NaN'})['result'],'Unable to Assess')
    def test_date_age(self):
        r=execute_rule(executable(calculation_logic={'method':'date_age','field':'review_date'}),{'review_date':'2026-10-01'},date(2026,10,13))
        self.assertEqual(r['observed_value'],12)
    def test_document_check_missing_vs_absent(self):
        rule=executable(calculation_logic={'method':'document_presence','document_key':'financials'},operator='equals',threshold_value=True)
        self.assertEqual(execute_rule(rule,{})['result'],'Unable to Assess')
        self.assertEqual(execute_rule(rule,{'documents':[]})['result'],'Breach')
        self.assertEqual(execute_rule(rule,{'documents':['financials']})['result'],'Pass')
    def test_between_list_and_existence(self):
        self.assertEqual(execute_rule(executable(operator='between',lower_bound=50,upper_bound=100),{'exposure':75})['result'],'Pass')
        self.assertEqual(execute_rule(executable(operator='in_list',threshold_value=['A','AA']),{'exposure':'AA'})['result'],'Pass')
        self.assertEqual(execute_rule(executable(operator='exists',threshold_value=None),{})['result'],'Unable to Assess')
    def test_currency_mismatch_does_not_compare_amounts(self):
        rule=executable(threshold_unit='USD')
        self.assertEqual(execute_rule(rule,{'currency':'INR','exposure':10})['result'],'Unable to Assess')
    def test_explicit_unit_magnitude(self):
        r=execute_rule(executable(threshold_unit='USD millions',threshold_value=100),{'currency':'USD','exposure':75000000})
        self.assertEqual(r['observed_value'],75)
        self.assertEqual(r['result'],'Pass')
    def test_missing_does_not_exist_is_not_pass(self):
        self.assertEqual(execute_rule(executable(operator='does_not_exist',threshold_value=None),{})['result'],'Unable to Assess')
    def test_absent_document_inventory_is_breach(self):
        rule=executable(calculation_logic={'method':'document_presence','document_key':'financials'},operator='equals',threshold_value=True,evidence_requirements=[{'key':'financials','description':'Financial statements','type':'document'}])
        self.assertEqual(execute_rule(rule,{'documents':[]})['result'],'Breach')
    def test_manual_and_missing_severity(self):
        self.assertEqual(execute_rule(executable(calculation_logic={'method':'manual'}),{})['result'],'Manual Review Required')
        self.assertEqual(execute_rule(executable(severity=None),{'exposure':101})['result'],'Manual Review Required')
    def test_conflicting_evidence_requires_human(self):
        r=execute_rule(executable(evidence_requirements=[{'key':'financials','description':'Accounts','type':'document'}]),{'exposure':10,'evidence':[{'key':'financials','conflicting':True}]})
        self.assertEqual(r['result'],'Manual Review Required')

class InventoryJobTests(unittest.TestCase):
    @patch('app.services.inventory_operations.run_quality_reviews',return_value={})
    @patch('app.services.rule_extraction.shared_policy_connection')
    @patch('app.risk_knowledge.pipeline.process_policy')
    def test_policy_failure_does_not_stop_other_policies(self,process,db,quality):
        import json
        from app.services.rule_extraction import run_inventory_job
        connection=db.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value={'policy_ids':[1,2,3]}
        def result(policy_id,user,job_id,callback):
            callback(1)
            if policy_id==2:raise TimeoutError()
            return {'policy_id':policy_id,'status':'Completed','rules_proposed':1,'validation_failures':0}
        process.side_effect=result
        run_inventory_job('00000000-0000-0000-0000-000000000001',{'user_id':'admin'})
        calls=connection.execute.call_args_list
        final=next(c for c in reversed(calls) if 'finished_at=' in c.args[0])
        self.assertEqual(final.args[1][0],'Completed with errors')
        reports=[json.loads(c.args[1][1]) for c in calls if 'report=%s' in c.args[0]]
        self.assertEqual(reports[-1]['policies_processed'],2)
        self.assertEqual(reports[-1]['policies_failed'],1)

    @patch('app.services.inventory_operations.run_quality_reviews',return_value={'quality_failed':1})
    @patch('app.services.rule_extraction.shared_policy_connection')
    @patch('app.risk_knowledge.pipeline.process_policy')
    def test_retry_skips_completed_documents_but_retains_their_counts(self,process,db,quality):
        import json
        from app.services.rule_extraction import run_inventory_job
        connection=db.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value={'policy_ids':[1,2],'progress':[
            {'policy_id':1,'status':'Completed','rules_proposed':5,'pipeline':'policy-semantic-llm-v1'},
            {'policy_id':2,'status':'Completed','partial_result':True,'rules_proposed':2}]}
        process.return_value={'policy_id':2,'status':'Completed','rules_proposed':3}
        run_inventory_job('job-1',{'user_id':'analyst'})
        process.assert_called_once()
        self.assertEqual(process.call_args.args[0],2)
        final=next(c for c in reversed(connection.execute.call_args_list) if 'finished_at=' in c.args[0])
        self.assertEqual(final.args[1][0],'Completed')
        report=json.loads(final.args[1][1])
        self.assertEqual(report['rules_proposed'],8)
        self.assertEqual(report['policies_processed'],2)
        quality.assert_not_called()

    @patch('app.services.inventory_operations.run_quality_reviews',side_effect=ValueError('Review unavailable'))
    @patch('app.services.rule_extraction.shared_policy_connection')
    @patch('app.risk_knowledge.pipeline.process_policy')
    def test_graph_first_job_does_not_require_model_quality_review(self,process,db,quality):
        from app.services.rule_extraction import run_inventory_job
        connection=db.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value={'policy_ids':[1]}
        process.return_value={'policy_id':1,'status':'Completed','rules_proposed':3}
        with patch('app.services.rule_extraction.logger'):
            run_inventory_job('job-1',{'user_id':'analyst'})
        final=next(c for c in reversed(connection.execute.call_args_list) if 'finished_at=' in c.args[0])
        self.assertEqual(final.args[1][0],'Completed')
        quality.assert_not_called()

    @patch('app.services.inventory_operations.run_quality_reviews',return_value={})
    @patch('app.services.rule_extraction.shared_policy_connection')
    @patch('app.risk_knowledge.pipeline.process_policy')
    def test_long_model_calls_keep_job_alive_without_waiting_for_a_batch(self,process,db,quality):
        from app.services.rule_extraction import run_inventory_job
        connection=db.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value={'policy_ids':[1]}
        process.return_value={'policy_id':1,'status':'Completed','rules_proposed':1}
        with patch('threading.Event') as event,patch('threading.Thread') as thread, \
             patch('app.services.rule_extraction._process_inventory_job'):
            event.return_value.wait.side_effect=[False,True]
            def start():
                thread.call_args.kwargs['target']()
            thread.return_value.start.side_effect=start
            run_inventory_job('job-1',{'user_id':'analyst'})
            event.return_value.set.assert_called_once()
            thread.return_value.join.assert_called_once()
        self.assertTrue(any("WHERE id=%s AND status='Running'" in c.args[0] for c in connection.execute.call_args_list))
    @patch('app.services.rule_extraction.shared_policy_connection')
    @patch('app.risk_knowledge.pipeline.process_policy')
    def test_unclaimed_job_does_not_run_twice(self,process,db):
        from app.services.rule_extraction import run_inventory_job
        db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value=None
        run_inventory_job('00000000-0000-0000-0000-000000000001',{'user_id':'admin'})
        process.assert_not_called()

class DevelopmentApprovalTests(unittest.TestCase):
    @patch('app.routers.rules.RULE_DEMO_AUTO_APPROVE',False)
    def test_demo_approval_disabled_in_production(self):
        from app.routers.rules import demo_approve
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:demo_approve(1,{'user_id':'admin','role':'admin'})
        self.assertEqual(error.exception.status_code,403)
    @patch('app.routers.rules.RULE_DEMO_AUTO_APPROVE',True)
    @patch('app.routers.rules.shared_policy_connection')
    def test_imported_policies_cannot_use_demo_approval(self,db):
        from app.routers.rules import demo_approve
        from fastapi import HTTPException
        db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'source_type':'imported','status':'Draft'}
        with self.assertRaises(HTTPException) as error:demo_approve(1,{'user_id':'admin','role':'admin'})
        self.assertEqual(error.exception.status_code,403)

if __name__=='__main__':unittest.main()
