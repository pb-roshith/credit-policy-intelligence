"""Deterministic checks. No executable expressions or model arithmetic."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import operator
import re
import math

ENGINE_VERSION = '2.1.0'
MISSING = object()


def field_value(data, path):
    value = data
    for name in path.split('.'):
        if not isinstance(value,dict) or name not in value:
            return MISSING
        value = value[name]
    return MISSING if value is None else value


def numeric(value):
    if isinstance(value,bool):
        raise ValueError('Boolean is not a numerical metric')
    n = Decimal(str(value))
    if not n.is_finite():
        raise ValueError('Metric must be finite')
    return n


def compare(actual, op, expected):
    if actual is MISSING: return None
    if op=='exists': return actual is not None and actual is not False
    if op=='does_not_exist': return actual is None or actual is False
    if op=='between':
        return numeric(expected[0])<=numeric(actual)<=numeric(expected[1])
    if op in ('in_list','not_in_list'):
        result = actual in expected
        return result if op=='in_list' else not result
    functions={'equals':operator.eq,'not_equals':operator.ne,'greater_than':operator.gt,'greater_than_or_equal':operator.ge,'less_than':operator.lt,'less_than_or_equal':operator.le}
    if op not in functions: raise ValueError('Unsupported comparison')
    # Explicit ordered rating scale; never numerically cast a credit rating.
    ratings = ('D','C','CC','CCC-','CCC','CCC+','B-','B','B+','BB-','BB','BB+','BBB-','BBB','BBB+','A-','A','A+','AA-','AA','AA+','AAA')
    if op not in ('equals','not_equals') and isinstance(actual,str) and isinstance(expected,str) and actual in ratings and expected in ratings:
        return functions[op](ratings.index(actual),ratings.index(expected))
    if op not in ('equals','not_equals') or isinstance(expected,(int,float,Decimal)) and not isinstance(expected,bool):
        actual,expected = numeric(actual),numeric(expected)
    return functions[op](actual,expected)


def condition_result(condition, data):
    """Three-valued logic: missing attributes never imply applicability."""
    if not condition: return True,[],['No additional applicability restrictions']
    if 'all' in condition and condition['all'] is not None or 'any' in condition and condition['any'] is not None:
        conjunction = condition.get('all') is not None
        results=[condition_result(c,data) for c in condition['all' if conjunction else 'any']]
        values=[r[0] for r in results]
        outcome = (False if False in values else None if None in values else True) if conjunction else (True if True in values else None if None in values else False)
        return outcome,sorted(set(k for r in results for k in r[1])),[f"{'AND' if conjunction else 'OR'} condition"]+[s for r in results for s in r[2]]
    field=condition['field']; actual=field_value(data,field)
    try: result=compare(actual,condition['operator'],condition.get('value'))
    except (ValueError,TypeError,InvalidOperation): result=None
    reason=f"{field}: {'Unavailable' if actual is MISSING else actual}; {condition['operator']} {condition.get('value')}"
    return result,[field] if result is None else [],[reason]


def calculate(logic,data,as_of):
    method=logic['method']; missing=[]
    def value(key):
        v=field_value(data,key)
        if v is MISSING: missing.append(key)
        return v
    if method=='manual': return MISSING,[], 'Human judgment required'
    if method=='compound':
        outcome,missing,reasons=condition_result(logic['condition'],data)
        return MISSING if outcome is None else outcome,missing if outcome is None else [],'; '.join(reasons)
    if method=='document_presence':
        key=logic['document_key']
        documents=value('documents')
        if documents is MISSING: return MISSING,missing,f'Document presence: {key}'
        if not isinstance(documents,(list,dict)): return MISSING,['documents'],f'Invalid document evidence: {key}'
        if isinstance(documents,dict):
            item=documents.get(key,MISSING)
            if item is MISSING: return False,[],f'Document presence: {key}'
            if isinstance(item,dict): return item.get('present',True),[],f'Document presence: {key}'
            return bool(item),[],f'Document presence: {key}'
        return key in documents,[],f'Document presence: {key}'
    if method in ('ratio','percentage'):
        numerator,denominator=value(logic['numerator']),value(logic['denominator'])
        if missing: return MISSING,missing,f"{logic['numerator']} / {logic['denominator']}"
        divisor=numeric(denominator)
        if divisor==0: return MISSING,[logic['denominator']+' (zero denominator)'],'Division unavailable'
        result=numeric(numerator)/divisor
        if method=='percentage': result*=100
        calculated=float(result)
        if not math.isfinite(calculated):raise ValueError('Calculated metric exceeds supported range')
        return calculated,[],f"{logic['numerator']} / {logic['denominator']}"+(' * 100' if method=='percentage' else '')
    actual=value(logic['field'])
    if method=='date_age':
        end=value(logic['as_of_field']) if logic.get('as_of_field') else as_of.isoformat()
        if missing: return MISSING,missing,'Date age in days'
        actual=(date.fromisoformat(str(end)[:10])-date.fromisoformat(str(actual)[:10])).days
    return actual,missing, f"{method}: {logic.get('field')}"


def referenced_fields(definition):
    fields=set(definition.get('input_data_fields',[]))
    logic=definition.get('calculation_logic') or {}
    fields.update(logic[key] for key in ('field','numerator','denominator','as_of_field') if logic.get(key))
    if logic.get('method')=='document_presence':fields.add('documents')
    def condition_fields(condition):
        if not condition:return
        if condition.get('field'):fields.add(condition['field'])
        for key in ('all','any'):
            for child in condition.get(key) or []:condition_fields(child)
    condition_fields(definition.get('applicability_conditions'));condition_fields(definition.get('applicability_exclusions'));condition_fields(logic.get('condition'))
    if definition.get('applicable_stage'):fields.add('status')
    if re.search(r'\b(USD|INR|EUR|GBP|JPY|CAD|AUD|CHF|CNY|AED|SGD|HKD)\b',definition.get('threshold_unit') or ''):fields.add('currency')
    return sorted(fields)


def execute_rule(definition,data,as_of=None):
    as_of=as_of or date.today()
    from ..agents.credit_request_policy_applicability import evaluate_conditions
    applicable,missing,reasons=evaluate_conditions(definition,data)
    result={'applicability':'Applicable' if applicable is True else 'Not Applicable' if applicable is False else 'Unable to Determine Applicability','applicability_reason':'; '.join(reasons),'input_values':{},'expected_threshold':definition.get('threshold_value'),'formula':definition.get('calculation_logic'),'observed_value':None,'variance':None,'result':'Not Applicable','severity':None,'missing_inputs':missing if applicable is None else [],'applicability_missing_inputs':missing,'engine_version':ENGINE_VERSION}
    for field in referenced_fields(definition):
        v=field_value(data,field);result['input_values'][field]=None if v is MISSING else v
    if applicable is False: return result
    if applicable is None: result['result']='Unable to Assess'; return result
    if any(e.get('conflicting') for e in data.get('evidence',[]) if e.get('key') in {r['key'] for r in definition.get('evidence_requirements',[])}):
        result['result']='Manual Review Required'; result['missing_inputs']=['Conflicting evidence'];return result
    required_evidence=definition.get('evidence_requirements',[])
    if any(e['type']=='human' for e in required_evidence):
        result['result']='Manual Review Required';return result
    # Evidence must be present explicitly, not inferred from an absent attachment list.
    evidence_by_key={e.get('key'):e for e in data.get('evidence',[])}
    for requirement in required_evidence:
        key=requirement['key']
        if requirement['type'] in ('document','approval') and key not in evidence_by_key:
            docs=data.get('documents')
            presence_check=(definition.get('calculation_logic') or {}).get('method')=='document_presence'
            if docs is None or (key not in docs and not presence_check): result['missing_inputs'].append('evidence:'+key)
        elif requirement['type']=='data' and field_value(data,key) is MISSING and key not in evidence_by_key:
            result['missing_inputs'].append(key)
    if result['missing_inputs']:
        result['result']='Unable to Assess'; return result
    logic=definition.get('calculation_logic')
    if not logic or logic['method']=='manual' or definition.get('operator') is None:
        result['result']='Manual Review Required'; return result
    threshold=definition.get('threshold_value')
    op=definition['operator']
    if op=='between': threshold=[definition.get('lower_bound'),definition.get('upper_bound')]
    if op not in ('exists','does_not_exist') and (threshold is None or op=='between' and None in threshold):
        result['result']='Unable to Assess';result['missing_inputs']=['Approved threshold'];return result
    unit=definition.get('threshold_unit') or ''
    currency=re.search(r'\b(USD|INR|EUR|GBP|JPY|CAD|AUD|CHF|CNY|AED|SGD|HKD)\b',unit)
    if currency and data.get('currency')!=currency.group(1):
        result['result']='Unable to Assess';result['missing_inputs']=['Matching currency data or an approved conversion rule'];return result
    try:
        actual,missing,formula=calculate(logic,data,as_of)
        if actual is not MISSING and logic['method']=='date_age':
            time_unit=unit.strip().lower()
            if time_unit in ('month','months','year','years'):
                from .credit_data import tenor_months
                end=field_value(data,logic['as_of_field']) if logic.get('as_of_field') else as_of.isoformat()
                actual=tenor_months(str(field_value(data,logic['field']))[:10],str(end)[:10])
                if time_unit in ('year','years'):actual/=12
                formula+='; contractual calendar '+time_unit
            elif time_unit not in ('','day','days','calendar days'):
                result['result']='Unable to Assess';result['missing_inputs']=['Approved calendar/unit conversion for '+unit];return result
        # A ratio with a percent threshold must be expressed on a 0..100 scale.
        if actual is not MISSING and logic['method']=='ratio' and unit.strip().lower() in ('%', 'percent', 'percentage'):
            actual *= 100; formula += ' * 100 (percent threshold)'
        if actual is not MISSING and logic['method']=='direct':
            for magnitude,divisor in (('billion',1000000000),('million',1000000),('thousand',1000)):
                if re.search(r'\b'+magnitude+r's?\b',unit,re.I):
                    actual=float(numeric(actual)/Decimal(divisor));formula+=f' / {divisor} ({unit})';break
        result['missing_inputs']=missing;result['calculation_performed']=formula
        result['observed_value']=None if actual is MISSING else actual
        passed=compare(actual,op,threshold)
        if passed is None:
            result['result']='Unable to Assess';return result
        result['expected_threshold']=threshold
        try:result['variance']=str(numeric(actual)-numeric(threshold))
        except (InvalidOperation,ValueError,TypeError):result['variance']=f'{actual} {op} {threshold}'
        if passed: result['result']='Pass';result['severity']='PASS'
        elif definition.get('severity') is None:result['result']='Manual Review Required'
        else:result['result']='Breach' if definition['severity']=='BREACH' else 'Warning';result['severity']=definition['severity']
    except (InvalidOperation,ValueError,TypeError,KeyError,OverflowError):
        result['result']='Unable to Assess';result['missing_inputs']=sorted(set(result['missing_inputs']+['Invalid calculation input']))
    return result
