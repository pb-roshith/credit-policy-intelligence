"""Illustrative actuals for already matched semantic rules, never for scope."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
from statistics import median
from ..services.semantic_matching import Facts, number, unit_spec

VERSION = 'semantic-demonstration-actuals-v1'


def sample_key(metric, unit, currency=None):
    family, _, code = unit_spec(unit)
    return '|'.join((metric, family, (code or currency or '') if family=='money' else ''))


def manufacture_actuals(request_id, proposal, matcher, decisions, as_of=None):
    """Use one sample per request/metric/unit family across all matched rules.

    Existing values, conflicting/ambiguous facts and unit mismatches are retained.
    Samples are separate assessment observations, not edits to request facts.
    """
    today=(as_of or date.today()).isoformat();facts=Facts(proposal);groups={}
    for decision in decisions:
        rid=decision['candidate_id']
        for tid in matcher.targets(rid,'HAS_THRESHOLD'):
            boundary=matcher.nodes[tid]['properties']
            for mid in matcher.targets(tid,'MEASURED_BY'):
                metric=matcher.nodes[mid]['properties']['metric_key']
                actual,_,source=facts.get(metric)
                if actual is not None or source.get('status') not in ('MISSING','MISSING_CANONICAL_FACT'):continue
                try:threshold=number(boundary['value'])
                except (ValueError,TypeError,ArithmeticError):continue
                family,scale,currency=unit_spec(boundary['unit'])
                key=sample_key(metric,boundary['unit'],proposal.get('currency'))
                group=groups.setdefault(key,{'metric':metric,'family':family,'currency':currency or proposal.get('currency'),
                    'unit':boundary['unit'],'values':[],'threshold_nodes':[]})
                group['values'].append(threshold*scale);group['threshold_nodes'].append(tid)
    result={}
    for key,group in groups.items():
        seed=sha256(f'{VERSION}:{request_id}:{key}'.encode()).digest()[0]
        anchor=median(group['values']);factor=(Decimal('.8'),Decimal('1'),Decimal('1.2'),Decimal('1.05'))[seed%4]
        value=anchor*factor if anchor else Decimal('1') if seed%2 else Decimal('0')
        unit={'money':group['currency'] or 'currency','months':'months','days':'days','ratio':'x','percent':'%','score':'score'}.get(group['family'],group['unit'])
        if group['family']=='score':value=value.quantize(Decimal('1'))
        source_id=f'{VERSION}:{request_id}:{sha256(key.encode()).hexdigest()[:16]}'
        result[key]={'field':group['metric'],'value':float(round(value,6)),'unit':unit,
            'source':'Manufactured Demonstration Data','source_type':'SYNTHETIC','verification_status':'MANUFACTURED',
            'source_identifier':source_id,'as_of_date':today,'generator_version':VERSION,
            'generation_method':'Deterministic sample around the median policy threshold; not an observed bank value',
            'reference_threshold_nodes':sorted(set(group['threshold_nodes']))}
    return result


def qualitative_observation(request_id, rule_id, as_of=None):
    return {'field':'qualitative_review','value':'Sample review record prepared; reviewer verification pending',
        'source':'Manufactured Demonstration Data','source_type':'SYNTHETIC','verification_status':'MANUFACTURED',
        'source_identifier':f'{VERSION}:{request_id}:{rule_id}:qualitative',
        'as_of_date':(as_of or date.today()).isoformat(),'generator_version':VERSION,
        'generation_method':'Illustrative control-review observation; does not establish compliance or approval'}
