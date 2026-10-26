"""Evidence templates describe frozen engine results without recalculation."""
import json
from typing import Any
from pydantic import BaseModel, ConfigDict


class ComplianceExplanationReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    short_summary: str
    detailed_explanation: str
    evidence_citations: list[dict[str, Any]]
    missing_information: list[str]
    next_required_action: str | None


class CreditPolicyComplianceExplanationAgent:
    name = 'Credit Policy Compliance Explanation Agent'
    prompt_version = 'credit-policy-compliance-explanation-v1'
    output_model = ComplianceExplanationReport

    def run(self, finding):
        outcome = finding['result']
        if outcome not in ('Pass', 'Warning', 'Breach', 'Not Applicable', 'Unable to Assess', 'Manual Review Required'):
            raise ValueError('An existing deterministic outcome is required')
        def rendered(value):
            return 'Not supplied' if value is None else json.dumps(value, default=str, ensure_ascii=False)
        citations = finding.get('evidence_references') or []
        missing = list(dict.fromkeys(finding.get('missing_inputs') or []))
        for key in ('policy_name','policy_version','source_clause','rule_version','workflow_stage','applicability_reason','input_values'):
            if finding.get(key) is None: missing.append(key)
        if not citations: missing.append('Evidence references not supplied')
        contradictory = [e for e in citations if e.get('conflicting')]
        if contradictory: missing.append('Contradictory evidence: ' + ', '.join(str(e.get('key')) for e in contradictory))
        policy = finding.get('policy_name') or 'Policy name not supplied'
        rule = finding.get('rule_name') or finding.get('policy_clause') or finding.get('rule_code') or 'Rule name not supplied'
        summary = f'{policy}: {rule} — {outcome}.'
        details = (f"Policy: {policy}, version {rendered(finding.get('policy_version'))}. "
            f"Source clause: {rendered(finding.get('source_clause'))}. "
            f"Rule: {rule}, version {rendered(finding.get('rule_version'))}. "
            f"Applicability: {rendered(finding.get('applicability_reason'))}. "
            f"Current workflow stage: {rendered(finding.get('workflow_stage'))}. "
            f"Observed input values: {rendered(finding.get('input_values'))}. "
            f"Formula used: {rendered(finding.get('calculation_performed') or finding.get('formula'))}. "
            f"Calculated value: {rendered(finding.get('observed_value'))}. "
            f"Threshold or required condition: {rendered(finding.get('expected_threshold'))}. "
            f"Operator: {rendered(finding.get('operator'))}; unit: {rendered(finding.get('threshold_unit'))}; "
            f"Check question: {rendered(finding.get('check_question'))}. "
            f"Result: {outcome}. Variance: {rendered(finding.get('variance'))}. "
            f"Evidence used: {rendered(citations)}. Missing or contradictory evidence: {rendered(missing)}.")
        action = finding.get('approval_or_escalation_requirement')
        if action: details += f' Required escalation or approval: {action}.'
        return ComplianceExplanationReport(short_summary=summary, detailed_explanation=details,
            evidence_citations=citations, missing_information=missing, next_required_action=action).model_dump()
