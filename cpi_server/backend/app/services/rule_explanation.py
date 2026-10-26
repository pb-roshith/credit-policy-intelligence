"""Compatibility entry point for structured explanations of frozen engine results."""
from ..agents.credit_policy_compliance_explanation import CreditPolicyComplianceExplanationAgent


def deterministic_explanation(finding):
    return CreditPolicyComplianceExplanationAgent().run(finding)['detailed_explanation']


def explain_findings(findings):
    agent = CreditPolicyComplianceExplanationAgent()
    for finding in findings:
        report = agent.run(finding)
        finding['explanation_report'] = report
        finding['explanation'] = report['detailed_explanation']
        finding['explanation_source'] = agent.name + ' (deterministic evidence template)'
    return findings
