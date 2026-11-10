"""Mistral-backed agent implementing the business extraction contract."""
import json
import re
from pathlib import Path
from app.ai_provider import AIClient as Mistral
from mistralai.client.utils.retries import RetryConfig,BackoffStrategy
from ..config import MISTRAL_API_KEY,MISTRAL_POLICY_MODEL,MISTRAL_TIMEOUT_MS
from ..telemetry import record_ai_call
from ..services.credit_policy_extraction_schema import CreditPolicyExtractionReport
from ..services.source_quantities import restore_stated_amount_units,source_unit_supported

AGENT_NAME='Credit Policy Rule Extraction Agent'
PROMPT_VERSION='credit-policy-rule-extraction-v6-source-units'
COMPATIBLE_CHECKPOINT_VERSIONS=('credit-policy-rule-extraction-v5-quantitative-compact',)
SYSTEM_PROMPT=(Path(__file__).parent/'credit_policy_rule_extraction_prompt.txt').read_text(encoding='utf-8-sig')

class SourceValidationError(ValueError):
    """Sanitized application error; never includes confidential source content."""


def clause_reference(clause):
    return str(clause.get('clause_number') or f"un-numbered span {clause['sequence']}")


def source_span(excerpt,source):
    if excerpt in source:return excerpt
    pattern=r'\s+'.join(re.escape(word) for word in excerpt.split())
    match=re.search(pattern,source) if pattern else None
    if match:return match.group(0)
    raise SourceValidationError('Supporting excerpt does not match supplied source')


def resolve_clause(rule,clauses):
    candidates=[c for c in clauses if clause_reference(c)==rule.source_clause]
    matches=[]
    for clause in candidates:
        try:matches.append((clause,source_span(rule.source_excerpt,clause['source_excerpt'])))
        except SourceValidationError:pass
    if len(matches)>1:
        matches=[item for item in matches if item[0].get('section_heading')==rule.source_section and item[0].get('page_number')==rule.source_page]
    if len(matches)!=1:raise SourceValidationError('Rule does not identify one exact supplied source span')
    return matches[0]


def validate_report(report,metadata,clauses):
    for key in ('policy_id','policy_version','source_document_id','extraction_run_id'):
        if getattr(report,key)!=metadata[key]:raise SourceValidationError('Extraction changed application identity metadata')
    seen=set();span_sequences={}
    for rule in report.rules:
        if rule.proposed_rule_code in seen:raise SourceValidationError('Duplicate proposed rule code')
        seen.add(rule.proposed_rule_code)
        clause,exact=resolve_clause(rule,clauses);rule.source_excerpt=exact
        if rule.source_section!=clause.get('section_heading') or rule.source_page!=clause.get('page_number'):
            report.processing_warnings.append(f'{rule.proposed_rule_code}: section/page restored from registered source metadata')
        rule.source_section=clause.get('section_heading');rule.source_page=clause.get('page_number')
        prefix=f"POL-{metadata['policy_id']}-C{clause['sequence']}-R"
        if not re.fullmatch(re.escape(prefix)+r'[1-9]\d*',rule.proposed_rule_code):
            raise SourceValidationError('Rule code does not match its supplied source prefix')
        sequence=int(rule.proposed_rule_code[len(prefix):]);span_sequences.setdefault(clause['id'],[]).append(sequence)
        source=clause['source_excerpt'];normalized=' '.join(source.lower().split())
        if restore_stated_amount_units(rule,rule.source_excerpt):
            report.processing_warnings.append(f'{rule.proposed_rule_code}: amount restored to the exact quoted source magnitude/unit')
        numeric=[]
        for value in (rule.threshold_value,rule.lower_bound,rule.upper_bound):
            values=value if isinstance(value,list) else [value]
            numeric.extend(v for v in values if isinstance(v,(float,int)) and not isinstance(v,bool))
        tokens={float(t.replace(',','')) for t in re.findall(r'(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?',rule.source_excerpt)}
        if any(float(value) not in tokens for value in numeric):
            raise SourceValidationError('Threshold is not explicitly present in its supporting excerpt')
        if isinstance(rule.threshold_value,str) and rule.threshold_value.lower() not in normalized:
            raise SourceValidationError('Categorical threshold is absent from the source')
        # Do not turn plausible evidence, sources or authorities into claimed facts.
        for property_name in ('data_sources','evidence_requirements'):
            retained=[]
            for value in getattr(rule,property_name):
                if ' '.join(value.lower().split()) in normalized:retained.append(value)
                else:report.processing_warnings.append(property_name);report.processing_warnings.append(f'{rule.proposed_rule_code}: unsupported {property_name} omitted')
            setattr(rule,property_name,retained)
        for property_name in ('approval_or_escalation_requirement','breach_consequence'):
            value=getattr(rule,property_name)
            if value and ' '.join(value.lower().split()) not in normalized:
                setattr(rule,property_name,None);report.processing_warnings.append(property_name)
        for field in rule.input_data_fields:
            if field.definition and ' '.join(field.definition.lower().split()) not in normalized:
                field.definition=None;report.processing_warnings.append('input definition:'+field.field_name)
            if field.unit and field.unit.lower() not in normalized:
                percentage=field.unit.lower() in ('%','percent','percentage') and ('%' in source or 'percent' in normalized)
                if not percentage:field.unit=None;report.processing_warnings.append('input unit:'+field.field_name)
        if rule.threshold_unit and rule.threshold_unit.lower() not in normalized:
            percentage=rule.threshold_unit.lower() in ('%','percent','percentage') and ('%' in source or 'percent' in normalized)
            explicit_amount=source_unit_supported(rule.threshold_unit,rule.source_excerpt,numeric)
            if not percentage and not explicit_amount:rule.threshold_unit=None;report.processing_warnings.append('threshold_unit')
        retained_stages=[]
        for stage in rule.applicable_stages:
            if ' '.join(stage.lower().split()) in normalized:retained_stages.append(stage)
            else:
                report.processing_warnings.append('applicable_stages')
                report.processing_warnings.append(f'{rule.proposed_rule_code}: unsupported workflow stage omitted')
        rule.applicable_stages=retained_stages
        if rule.severity:
            severity=rule.severity.lower()
            if not re.search(r'\bseverity\s*[:=| -]*'+severity+r'\b|\b'+severity+r'\s+severity\b',normalized):
                rule.severity=None;report.processing_warnings.append('severity')
        if rule.threshold_type:
            support={'HARD_LIMIT':r'\bhard limit\b|\b(?:must|shall) not exceed\b','WARNING':r'\bwarning\b','TARGET':r'\btarget\b'}
            if not re.search(support[rule.threshold_type],normalized):
                rule.threshold_type=None;report.processing_warnings.append('threshold_type')
        if rule.exception_allowed!='NOT_STATED' and 'exception' not in normalized:
            rule.exception_allowed='NOT_STATED';report.processing_warnings.append('exception_allowed')
        if rule.operator=='MANUAL_ASSESSMENT' or rule.ambiguities or rule.mandatory is None:
            rule.ambiguities=list(dict.fromkeys(rule.ambiguities+['Manual Review Required']))
    for sequences in span_sequences.values():
        if sorted(sequences)!=list(range(1,len(sequences)+1)):
            raise SourceValidationError('Atomic rule sequences must be consecutive within a source span')
    references={clause_reference(c) for c in clauses}
    for content in report.non_rule_content:
        if content.source_clause not in references:raise SourceValidationError('Non-rule content references an unknown clause')
    # Related rules may be outside this batch; preserve the dependency, flag the missing source.
    for rule in report.rules:
        unresolved=[code for code in rule.related_rule_codes if code not in seen]
        if unresolved:report.processing_warnings.extend(f'Unresolved related rule: {code}' for code in unresolved)
    report.processing_warnings=list(dict.fromkeys(report.processing_warnings))
    return report


class CreditPolicyRuleExtractionAgent:
    name=AGENT_NAME
    prompt_version=PROMPT_VERSION
    output_schema=CreditPolicyExtractionReport

    def __init__(self,client_factory=Mistral,api_key=None):
        self.client_factory=client_factory
        self.api_key=MISTRAL_API_KEY if api_key is None else api_key

    def run(self,*,policy_id,policy_version,source_document_id,extraction_run_id,clauses,previous_validation_error=None,knowledge_context=None):
        if not self.api_key:raise ValueError('Mistral API key is not configured')
        if not clauses or len(clauses)>10 or sum(len(c['source_excerpt']) for c in clauses)>18000:
            raise ValueError('Supply a nonempty, bounded clause group')
        metadata={'policy_id':str(policy_id),'policy_version':policy_version,'source_document_id':str(source_document_id),'extraction_run_id':str(extraction_run_id)}
        payload=[{'source_clause':clause_reference(c),'source_section':c.get('section_heading'),'source_page':c.get('page_number'),'rule_code_prefix':f"POL-{policy_id}-C{c['sequence']}-R",'source_excerpt':c['source_excerpt'],'exact_quote_candidates':[part.strip() for part in re.split(r'(?<=[.;!?])\s+',c['source_excerpt']) if part.strip()]} for c in clauses]
        content={'application_metadata':metadata,'source_clauses':payload,'previous_validation_error':previous_validation_error}
        system=SYSTEM_PROMPT
        if knowledge_context is not None:
            if len(json.dumps(knowledge_context))>20000:
                raise ValueError('Risk knowledge context exceeds the extraction limit')
            content['risk_knowledge_context']=knowledge_context
            system+='\nRisk knowledge context is vocabulary assistance only. SOURCE schema entries are not approved mappings. Derive every requirement and threshold solely from the supplied policy clauses. Never treat taxonomy values or ontology relationships as policy requirements. Preserve original field terminology and source wording.'
        with self.client_factory(api_key=self.api_key,timeout_ms=MISTRAL_TIMEOUT_MS) as client:
            response=record_ai_call('Policy Rule Library','rule_extraction',client.chat.parse,telemetry_target=str(policy_id),model=MISTRAL_POLICY_MODEL,response_format=self.output_schema,messages=[{'role':'system','content':system},{'role':'user','content':json.dumps(content,default=str)}],tools=[],temperature=0,max_tokens=16000,retries=RetryConfig('none',BackoffStrategy(0,0,1,0),False))
        report=response.choices[0].message.parsed
        if not isinstance(report,self.output_schema):raise SourceValidationError('Mistral did not return the typed extraction contract')
        report=validate_report(report,metadata,clauses)
        from ..services.quantitative_rules import is_quantitative_rule
        report.rules=[r for r in report.rules if is_quantitative_rule(dict(
            rule_type="quantitative",threshold_value=r.threshold_value,
            lower_bound=r.lower_bound,upper_bound=r.upper_bound))]
        return report
