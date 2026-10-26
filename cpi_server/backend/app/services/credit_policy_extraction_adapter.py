"""Conservative translation into the governed inventory; no text is evaluated as code."""
import json
import re
from ..agents.credit_policy_rule_extraction import resolve_clause
from .inventory_schema import ExtractionOutput,ProposedRule
from .quantitative_rules import is_quantitative_rule

OPERATOR_MAP={'EQ':'equals','NE':'not_equals','GT':'greater_than','GTE':'greater_than_or_equal','LT':'less_than','LTE':'less_than_or_equal','BETWEEN':'between','IN':'in_list','NOT_IN':'not_in_list','EXISTS':'exists','NOT_EXISTS':'does_not_exist'}
PATH=r'[A-Za-z][A-Za-z0-9_.]*'


def safe_calculation(formula,fields):
    if formula is None:return None
    expression=formula.strip()
    if expression in fields:return {'method':'direct','field':expression}
    ratio=re.fullmatch(r'\(?\s*('+PATH+r')\s*/\s*('+PATH+r')\s*\)?\s*(\*\s*100)?',expression)
    if ratio and ratio.group(1) in fields and ratio.group(2) in fields:
        return {'method':'percentage' if ratio.group(3) else 'ratio','numerator':ratio.group(1),'denominator':ratio.group(2)}
    return None


def to_inventory(report,clauses):
    output=[]
    retained=[r for r in report.rules if is_quantitative_rule(dict(
        rule_type="quantitative", threshold_value=r.threshold_value,
        lower_bound=r.lower_bound, upper_bound=r.upper_bound))]
    by_code={r.proposed_rule_code:resolve_clause(r,clauses)[0] for r in retained}
    for rule in retained:
        clause,_=resolve_clause(rule,clauses)
        sequence=int(rule.proposed_rule_code.rsplit('-R',1)[1])
        fields=[f.field_name for f in rule.input_data_fields]
        calculation=safe_calculation(rule.calculation_logic,fields)
        missing=[];ambiguities=list(rule.ambiguities)
        if rule.calculation_logic and calculation is None:
            ambiguities.append('Manual Review Required: captured formula needs an approved calculation mapping')
            missing.append('executable calculation mapping')
        conditions=[];unresolved=False
        for condition in rule.applicability_conditions:
            operator=OPERATOR_MAP.get(condition.operator.upper())
            if operator is None:
                unresolved=True;missing.append('applicability operator:'+condition.attribute);continue
            value=condition.value
            try:
                if operator in ('greater_than','greater_than_or_equal','less_than','less_than_or_equal','between','in_list','not_in_list'):
                    value=json.loads(value)
                if operator in ('between','in_list','not_in_list') and not isinstance(value,list):raise ValueError()
                conditions.append({'field':condition.attribute,'operator':operator,'value':value})
            except (ValueError,TypeError):
                unresolved=True;missing.append('applicability value:'+condition.attribute)
        applicability=conditions[0] if len(conditions)==1 else None
        if len(conditions)>1:
            if rule.relationship_logic in ('AND','OR'):
                applicability={'all' if rule.relationship_logic=='AND' else 'any':conditions}
            else:unresolved=True;missing.append('applicability condition logic')
        dependencies=[]
        for code in rule.related_rule_codes:
            related=by_code.get(code)
            if related and rule.relationship_logic in ('AND','OR'):
                dependencies.append({'clause_id':related['id'],'rule_sequence':int(code.rsplit('-R',1)[1]),'relationship':rule.relationship_logic})
            elif rule.relationship_logic!='INDEPENDENT':
                missing.append('dependency mapping:'+code)
                ambiguities.append('Manual Review Required: unresolved related rule '+code)
        evidence=[]
        for description in rule.evidence_requirements:
            text=description.lower()
            kind='approval' if 'approval' in text else 'document' if re.search(r'document|statement|memo|valuation|certificate|legal|record',text) else 'data' if any(field.replace('_',' ') in text for field in fields) else 'human'
            key=re.sub(r'[^a-z0-9]+','_',text).strip('_')[:200]
            evidence.append({'key':key,'description':description,'type':kind})
        category='quantitative'
        manual=rule.operator in (None,'MANUAL_ASSESSMENT') or calculation is None or bool(ambiguities) or unresolved
        if manual:calculation={'method':'manual'}
        kind='mandatory' if rule.mandatory is True else 'conditional' if rule.applicability_conditions else 'target' if rule.threshold_type=='TARGET' else 'unspecified'
        output.append(ProposedRule(clause_id=clause['id'],rule_sequence=sequence,rule_name=rule.rule_name,rule_description=rule.rule_description,source_excerpt=rule.source_excerpt,requirement_kind=kind,rule_type=category,check_question=rule.check_question,
            metric_name=rule.metric_name,metric_definition=rule.metric_definition,operator=OPERATOR_MAP.get(rule.operator),threshold_value=rule.threshold_value,threshold_unit=rule.threshold_unit,lower_bound=rule.lower_bound,upper_bound=rule.upper_bound,
            threshold_source=rule.source_excerpt if rule.threshold_value is not None or rule.lower_bound is not None or rule.upper_bound is not None else None,
            calculation_logic=calculation,input_data_fields=fields,data_source='; '.join(rule.data_sources) or None,evidence_requirements=evidence,
            applicability_conditions=applicability,applicability_unresolved=unresolved,applicable_stage=rule.applicable_stages or None,
            severity=None,breach_consequence=rule.breach_consequence,exception_allowed={'YES':True,'NO':False,'NOT_STATED':None}[rule.exception_allowed],approval_or_escalation_requirement=rule.approval_or_escalation_requirement,
            extraction_confidence=rule.extraction_confidence,extraction_notes='; '.join(ambiguities) or None,missing_information=sorted(set(missing)),dependencies=dependencies,
            requirement_category="QUANTITATIVE",mandatory=rule.mandatory,threshold_type=rule.threshold_type,risk_severity=rule.severity,source_rule_code=rule.proposed_rule_code,
            input_field_definitions=[f.model_dump() for f in rule.input_data_fields],data_sources=rule.data_sources,ambiguities=ambiguities,review_label='Manual Review Required' if manual or rule.mandatory is None else 'Human Review Required',source_calculation_logic=rule.calculation_logic))
    return ExtractionOutput(rules=output)
