import copy
import unittest
from app.risk_knowledge.demo import SAMPLE_REQUEST, demo_concepts
from app.risk_knowledge.evaluation import evaluate_rule, evaluate_expression
from app.risk_knowledge.models import Condition, CreditRequest, Expression, Outcome, Provenance, Rule
from app.risk_knowledge.taxonomy import TaxonomyService


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = TaxonomyService(demo_concepts())
        self.request = CreditRequest.model_validate(copy.deepcopy(SAMPLE_REQUEST))

    def condition(self, key, op, value, unit=None):
        return Condition(attribute=key, operator=op, value=value, unit=unit, original_term=key,
                         taxonomy_mapping='DEMO-' + key, normalized_term=key)

    def evaluate(self, expression):
        return evaluate_expression(expression, self.request, self.taxonomy)['result']

    def rule(self, expression, **kwargs):
        return Rule(rule_id='TEST-1', rule_name='Test', rule_type='APPROVAL',
                    conditions=expression, outcome=Outcome(action='Approval Required', authority='Committee'),
                    policy=Provenance(document_id='DEMO', document_name='synthetic', origin='SYNTHETIC_DEMO', passage='Test clause', effective_date='2026-10-01'),
                    clause_id='CLAUSE', status='APPROVED', validation={'test_fixture_validated': True}, requires_review=False, **kwargs)

    def test_numeric_strict_boundary(self):
        c = self.condition('amount', '>', 5000000, 'INR')
        self.request.attributes['amount'] = 5000000
        self.assertIs(self.evaluate(Expression(conditions=[c])), False)
        self.request.attributes['amount'] = 5000001
        self.assertIs(self.evaluate(Expression(conditions=[c])), True)

    def test_inclusive_threshold(self):
        self.request.attributes['amount'] = 5000000
        self.assertTrue(self.evaluate(Expression(conditions=[self.condition('amount', '>=', 5000000, 'INR')])))

    def test_decimal_precision(self):
        self.request.attributes['amount'] = '5000000.01'
        self.assertTrue(self.evaluate(Expression(conditions=[self.condition('amount', '>', '5000000.00', 'INR')])))

    def test_rating_order_not_alphabetical(self):
        for actual, expected, result in [('BB','BBB',True),('AA','A',False),('AAA','BBB',False),('B','BB',True)]:
            with self.subTest(actual=actual):
                self.request.attributes['rating'] = actual
                self.assertIs(self.evaluate(Expression(conditions=[self.condition('rating','<',expected)])), result)

    def test_unknown_rating(self):
        self.request.attributes['rating'] = 'UNRATED'
        self.assertIsNone(self.evaluate(Expression(conditions=[self.condition('rating','<','BBB')])))

    def test_rating_scale_requires_approval(self):
        self.taxonomy.by_id['DEMO-rating'].status = 'AI_PROPOSED'
        self.assertIsNone(self.evaluate(Expression(conditions=[self.condition('rating','<','BBB')])))

    def test_missing_rating_order(self):
        self.taxonomy.by_id['DEMO-rating'].metadata.pop('rating_order')
        self.assertIsNone(self.evaluate(Expression(conditions=[self.condition('rating','<','BBB')])))

    def test_and_conditions(self):
        e=Expression(conditions=[self.condition('amount','>',5000000,'INR'),self.condition('rating','<','BBB')])
        self.assertTrue(self.evaluate(e))
        self.request.attributes['rating']='A'
        self.assertFalse(self.evaluate(e))

    def test_or_conditions(self):
        e=Expression(logic='OR',conditions=[self.condition('industry','=','Manufacturing'),self.condition('industry','=','Construction')])
        self.assertTrue(self.evaluate(e))
        self.request.attributes['industry']='Services'
        self.assertFalse(self.evaluate(e))

    def test_nested_and_or(self):
        e=Expression(conditions=[self.condition('amount','>',5000000,'INR')],groups=[Expression(logic='OR',conditions=[self.condition('rating','=','BB'),self.condition('rating','=','B')])])
        self.assertTrue(self.evaluate(e))

    def test_missing_attribute(self):
        del self.request.attributes['amount']
        rule=self.rule(Expression(conditions=[self.condition('amount','>',5000000,'INR')]))
        self.assertEqual(evaluate_rule(rule,self.request,self.taxonomy)['status'],'INSUFFICIENT_DATA')

    def test_unknown_and_false_is_false(self):
        del self.request.attributes['amount']
        self.assertFalse(self.evaluate(Expression(conditions=[self.condition('amount','>',5,'INR'),self.condition('product','=','Secured Business Loan')])))

    def test_unknown_or_true_is_true(self):
        del self.request.attributes['amount']
        self.assertTrue(self.evaluate(Expression(logic='OR',conditions=[self.condition('amount','>',5,'INR'),self.condition('product','=','Unsecured Business Loan')])))

    def test_exception(self):
        rule=self.rule(Expression(conditions=[self.condition('amount','>',2000000,'INR')]),exceptions=[Expression(conditions=[self.condition('sovereign_guarantee','=',True)])])
        self.assertEqual(evaluate_rule(rule,self.request,self.taxonomy)['status'],'APPLICABLE')
        self.request.attributes['sovereign_guarantee']=True
        self.assertEqual(evaluate_rule(rule,self.request,self.taxonomy)['status'],'NOT_APPLICABLE')
        del self.request.attributes['sovereign_guarantee']
        self.assertEqual(evaluate_rule(rule,self.request,self.taxonomy)['status'],'INSUFFICIENT_DATA')

    def test_approved_vs_candidate_and_superseded(self):
        rule=self.rule(Expression(conditions=[self.condition('amount','>',5,'INR')]))
        for status in ['CANDIDATE','REVIEWED','REJECTED','SUPERSEDED']:
            rule.status=status
            self.assertEqual(evaluate_rule(rule,self.request,self.taxonomy)['status'],'EXCLUDED')

    def test_normalization_preserves_original(self):
        self.request.attributes['segment']='small business borrower'
        e=Expression(conditions=[self.condition('segment','=','SME')])
        result=evaluate_expression(e,self.request,self.taxonomy)
        self.assertTrue(result['result'])
        self.assertEqual(result['checks'][0]['actual'],'small business borrower')
        self.assertEqual(result['checks'][0]['normalized_actual'],'SME')

    def test_unapproved_synonym_does_not_normalize(self):
        self.taxonomy.by_id['DEMO-sme-alias'].status='AI_PROPOSED'
        self.request.attributes['segment']='small business borrower'
        self.assertIsNone(self.evaluate(Expression(conditions=[self.condition('segment','=','SME')])))

    def test_currency_mismatch(self):
        self.request.currency='USD'
        self.assertIsNone(self.evaluate(Expression(conditions=[self.condition('amount','>',5,'INR')])))

    def test_invalid_numeric_input(self):
        for value in [True,'NaN','Infinity','abc']:
            with self.subTest(value=value):
                self.request.attributes['amount']=value
                self.assertIsNone(self.evaluate(Expression(conditions=[self.condition('amount','>',5,'INR')])))

    def test_future_effective_policy(self):
        rule=self.rule(Expression(conditions=[self.condition('amount','>',5,'INR')]))
        rule.policy.effective_date='2027-01-01'
        self.assertEqual(evaluate_rule(rule,self.request,self.taxonomy)['status'],'NOT_APPLICABLE')

    def test_missing_boolean_does_not_mean_false(self):
        del self.request.attributes['sovereign_guarantee']
        self.assertIsNone(self.evaluate(Expression(conditions=[self.condition('sovereign_guarantee','=',False)])))

    def test_membership(self):
        self.assertTrue(self.evaluate(Expression(conditions=[self.condition('industry','in',['Manufacturing','Construction'])])))


if __name__=='__main__':
    unittest.main()
