import unittest
from app.agents.credit_policy_rule_extraction import validate_report,SourceValidationError
from app.services.credit_policy_extraction_schema import CreditPolicyExtractionReport
from app.services.credit_policy_extraction_adapter import to_inventory
from app.services.rule_extraction import validate_extraction
from test_credit_policy_extraction_agent import payload,clause


class SourceAmountTests(unittest.TestCase):
    def validate(self,value=500000000,unit='USD',text='Exposure shall not exceed USD 500 million.',**changes):
        data=payload()
        data['rules'][0].update(threshold_value=value,threshold_unit=unit,source_excerpt=text,**changes)
        source=clause();source['source_excerpt']=text
        metadata={key:data[key] for key in ('policy_id','policy_version','source_document_id','extraction_run_id')}
        report=validate_report(CreditPolicyExtractionReport.model_validate(data),metadata,[source])
        output=validate_extraction(to_inventory(report,[source]),[source])
        return report,output

    def test_expanded_currency_restored_through_both_validation_layers(self):
        report,output=self.validate()
        self.assertEqual(report.rules[0].threshold_value,500)
        self.assertEqual(report.rules[0].threshold_unit,'USD million')
        self.assertEqual(output.rules[0].threshold_unit,'USD million')
        self.assertEqual(output.rules[0].threshold_value,500)
        self.assertEqual(output.rules[0].source_excerpt,'Exposure shall not exceed USD 500 million.')

    def test_literal_amount_preserves_explicit_magnitude_in_unit(self):
        for unit in ('USD',None,'USD million'):
            report,_=self.validate(500,unit)
            self.assertEqual(report.rules[0].threshold_unit,'USD million')

    def test_range_endpoints_use_the_same_explicit_source_unit(self):
        report,output=self.validate(None,'USD','Exposure between USD 10 million and USD 50 million.',
                                    lower_bound=10000000,upper_bound=50000000,operator='BETWEEN')
        self.assertEqual((report.rules[0].lower_bound,report.rules[0].upper_bound),(10,50))
        self.assertEqual(output.rules[0].threshold_unit,'USD million')

    def test_invented_amount_currency_conflict_and_double_scaling_rejected(self):
        for value,unit,text in [(501000000,'USD','Exposure shall not exceed USD 500 million.'),
                                (500000000,'INR','Exposure shall not exceed USD 500 million.'),
                                (500000000,'USD million','Exposure shall not exceed USD 500 million.'),
                                (500000000,'USD','Exposure shall not exceed 500 USD.')]:
            with self.subTest(value=value,unit=unit,text=text),self.assertRaises(SourceValidationError):
                self.validate(value,unit,text)

    def test_range_can_share_an_explicit_currency_and_magnitude(self):
        for text in ('Exposure between USD 250 million to 999 million.',
                     'Exposure between USD 250 to 999 million.'):
            report,_=self.validate(None,'USD',text,lower_bound=250000000,upper_bound=999000000,operator='BETWEEN')
            self.assertEqual((report.rules[0].lower_bound,report.rules[0].upper_bound),(250,999))
            self.assertEqual(report.rules[0].threshold_unit,'USD million')

    def test_mixed_source_scales_cannot_share_one_threshold_unit(self):
        with self.assertRaises(SourceValidationError):
            self.validate(None,'USD','Exposure between USD 10 million and USD 1 billion.',
                          lower_bound=10000000,upper_bound=1000000000,operator='BETWEEN')

    def test_ordinary_unscaled_currency_is_unchanged(self):
        report,_=self.validate(100,'USD','Exposure shall not exceed 100 USD.')
        self.assertEqual((report.rules[0].threshold_value,report.rules[0].threshold_unit),(100,'USD'))

    def test_restored_magnitude_executes_without_double_conversion(self):
        from app.services.rule_engine import execute_rule
        _,output=self.validate()
        definition=output.rules[0].model_dump()
        definition.update(severity='BREACH',data_source='request.exposure')
        self.assertEqual(execute_rule(definition,{'currency':'USD','exposure':499000000})['result'],'Pass')
        self.assertEqual(execute_rule(definition,{'currency':'USD','exposure':501000000})['result'],'Breach')

    def test_old_draft_with_missing_magnitude_cannot_be_submitted(self):
        from app.risk_knowledge.pipeline import refresh_rule_evidence
        from test_inventory_pipeline import proposed
        definition=proposed(threshold_value=50,threshold_unit=None,source_excerpt='Approval is required above USD 50 million.')
        with self.assertRaisesRegex(ValueError,'Correct the threshold amount and unit'):
            refresh_rule_evidence({'definition':definition},{},None)
