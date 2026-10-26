"""Deterministic applicability only; evidence and compliance outcomes are excluded."""
from datetime import date
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict
from ..services.rule_engine import condition_result, field_value, MISSING


class ApplicabilityDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidate_id: str
    candidate_type: Literal['Policy', 'Rule']
    applicability: Literal['Applicable', 'Not Applicable', 'Unable to Determine']
    reason: str
    evaluated_attributes: dict[str, Any]
    missing_information: list[str]


class ApplicabilityReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evaluation_date: str
    current_stage: str | None
    decisions: list[ApplicabilityDecision]


def evaluate_conditions(definition, request_data):
    applicable, missing, reasons = condition_result(definition.get('applicability_conditions'), request_data)
    if definition.get('applicability_unresolved') and applicable is not False:
        applicable = None
        missing.append('Approved applicability mapping')
        reasons.append('Applicability needs human interpretation')
    stages = definition.get('applicable_stage') or definition.get('applicable_stages')
    if stages:
        stage = field_value(request_data, 'status')
        if stage is not MISSING and stage not in stages:
            applicable = False
        elif stage is MISSING and applicable is not False:
            applicable = None
            missing.append('status')
        reasons.append(f"Workflow stage: {'Unavailable' if stage is MISSING else stage}; allowed {stages}")
    return applicable, missing, reasons


class CreditRequestPolicyApplicabilityAgent:
    name = 'Credit Request Policy Applicability Agent'
    prompt_version = 'credit-request-policy-applicability-v1'
    output_model = ApplicabilityReport

    def run(self, request_data, candidates, current_stage, evaluation_date=None):
        today = evaluation_date or date.today()
        data = {**request_data, 'status': current_stage}
        results = []
        for candidate in candidates:
            definition = candidate.get('definition', candidate)
            applicable, missing, reasons = evaluate_conditions(definition, data)
            for key, lower in (('effective_from', True), ('effective_to', False), ('policy_effective_from', True)):
                if key=='policy_effective_from' and key not in candidate: continue
                value = candidate.get(key)
                if value is None:
                    if lower and applicable is not False:
                        applicable = None; missing.append(key)
                    continue
                try:
                    value = date.fromisoformat(str(value)[:10])
                    outside = today < value if lower else today > value
                    if outside:
                        applicable = False
                    reasons.append(f'{key}: {value}; assessment date: {today}')
                except ValueError:
                    if applicable is not False:
                        applicable = None
                    missing.append(key)
            fields = set()
            def collect(condition):
                if not condition: return
                if condition.get('field'): fields.add(condition['field'])
                for key in ('all', 'any'):
                    for child in condition.get(key) or []: collect(child)
            collect(definition.get('applicability_conditions'))
            if definition.get('applicable_stage') or definition.get('applicable_stages'): fields.add('status')
            attributes = {key: None if field_value(data, key) is MISSING else field_value(data, key) for key in sorted(fields)}
            results.append(ApplicabilityDecision(candidate_id=str(candidate['id']),
                candidate_type=candidate.get('candidate_type', 'Rule'),
                applicability='Applicable' if applicable is True else 'Not Applicable' if applicable is False else 'Unable to Determine',
                reason='; '.join(reasons), evaluated_attributes=attributes,
                missing_information=sorted(set(missing)) if applicable is None else []).model_dump())
        # A mapped policy is potentially applicable if any of its rules applies.
        # This aggregation uses applicability decisions only, never compliance outcomes.
        explicit_policies={r['candidate_id'] for r in results if r['candidate_type']=='Policy'}
        grouped={}
        for candidate, decision in zip(candidates, results):
            if decision['candidate_type']=='Rule' and candidate.get('policy_id') is not None:
                grouped.setdefault(str(candidate['policy_id']),[]).append(decision)
        for policy_id, rules in grouped.items():
            if policy_id in explicit_policies: continue
            values=[r['applicability'] for r in rules]
            outcome='Applicable' if 'Applicable' in values else 'Unable to Determine' if 'Unable to Determine' in values else 'Not Applicable'
            results.append(ApplicabilityDecision(candidate_id=policy_id,candidate_type='Policy',applicability=outcome,
                reason='Mapped rule applicability: '+'; '.join(f"{r['candidate_id']}: {r['applicability']}; {r['reason']}" for r in rules),
                evaluated_attributes={k:v for r in rules for k,v in r['evaluated_attributes'].items()},
                missing_information=sorted({k for r in rules for k in r['missing_information']}) if outcome=='Unable to Determine' else []).model_dump())
        return ApplicabilityReport(evaluation_date=today.isoformat(), current_stage=current_stage, decisions=results).model_dump()
