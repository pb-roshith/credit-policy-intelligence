"""Structured applicability, independent of AI-generated narratives."""
from ..agents.credit_request_policy_applicability import evaluate_conditions

class RequestApplicabilityAgent:
    def evaluate(self,rule_definition,request_data,evaluation_date):
        applicable,missing,reasons=evaluate_conditions(rule_definition,request_data)
        return {'applicability':'Applicable' if applicable is True else 'Not Applicable' if applicable is False else 'Unable to Determine', 'applicability_reason':'; '.join(reasons),'missing_information':missing if applicable is None else []}

    @staticmethod
    def policy_mapping(findings):
        applicable=[f for f in findings if f['applicability']=='Applicable']
        uncertain=[f for f in findings if f['applicability']=='Unable to Determine Applicability']
        result='Applicable' if applicable else 'Unable to Determine Applicability' if uncertain else 'Not Applicable'
        return result,'; '.join(dict.fromkeys(f['applicability_reason'] for f in findings))
