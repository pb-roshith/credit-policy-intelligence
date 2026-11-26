"""Canonical, evidence-backed facts. Policy definitions are never modified here."""
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import calendar
import json
import math
import re

from .rule_engine import referenced_fields, execute_rule, field_value, MISSING

SOURCE_TYPES = {'SYNTHETIC', 'MANUAL', 'DOCUMENT_EXTRACTED', 'BANK_SYSTEM', 'DERIVED'}
# Explicit semantic equivalences only. Ambiguous extracted names remain registered,
# unresolved requirements; they are not silently matched by fuzzy name similarity.
GROUPS = {
    'borrower.name': ['borrower_name'],
    'borrower.industry': ['industry'],
    'borrower.geography': ['geography'],
    'borrower.internal_rating': ['rating', 'internal_rating'],
    'borrower.external_rating': ['borrower_credit_rating', 'credit_rating'],
    'borrower.rating_evidence': ['credit_rating_verification'],
    'credit_request.request_id': ['credit_request_number', 'request_id'],
    'credit_request.workflow_stage': ['status'],
    'credit_request.requested_amount': ['requested_amount'],
    'credit_request.currency': ['currency'],
    'facility.facility_type': ['facility', 'facility_type'],
    'facility.loan_program':['loan_program'],
    'collateral.property_type':['property_type'],
    'collateral.vehicle_condition':['vehicle_condition'],
    'collateral.is_secured':['is_secured'],
    'facility.loan_purpose':['loan_purpose'],
    'approval.ltv_exception_applies':['ltv_exception_applies'],
    'regulatory.stricter_local_ltv_applies':['stricter_local_ltv_applies'],
    'facility.requested_amount': ['loan_amount'],
    'facility.tenor_months': ['tenor_months', 'facility_tenor_months', 'term_loan_tenor', 'revolving_credit_tenor', 'trade_finance_tenor', 'recommended_tenor_years'],
    'exposure.current_exposure': ['exposure'],
    'exposure.proposed_exposure': ['post_approval_exposure'],
    'financial.total_debt': ['total_debt'],
    'financial.ebitda': ['ebitda', 'EBITDA'],
    'financial.ebit': ['ebit', 'EBIT'],
    'financial.net_operating_income': ['net_operating_income'],
    'financial.debt_service': ['total_debt_service', 'annual_debt_service', 'debt_service'],
    'financial.interest_expense': ['interest_expense'],
    'financial.senior_debt': ['senior_debt'],
    'financial.total_debt_including_mezzanine': ['total_debt_including_mezzanine'],
    'metric.debt_to_ebitda': ['leverage_ratio', 'debt_to_ebitda', 'total_debt_ebitda_ratio_calculation'],
    'metric.dscr': ['dscr', 'debt_service_coverage_ratio', 'dscr_calculation'],
    'metric.interest_coverage': ['icr', 'icr_calculation'],
    'metric.ltv_percent': ['ltv', 'ltv_ratio', 'loan_to_value'],
    'collateral.valuation_amount': ['collateral_value', 'appraised_value'],
    'collateral.collateral_type': ['collateral_type'],
    'collateral.valuation_date': ['valuation_date', 'collateral_valuation_date'],
    'collateral.haircut_percent': ['haircut_percentage'],
    'collateral.eligible_value': ['adjusted_collateral'],
    'approval.approving_authority': ['approval_authority'],
    'risk.breach_trigger': ['breach_trigger'],
    'risk.warning_trigger': ['warning_trigger'],
    'documentation.documents': ['documents'],
}
ALIASES = {alias: canonical for canonical, aliases in GROUPS.items() for alias in aliases}
DERIVATIONS = {
    'facility.tenor_months': ['facility.start_date', 'facility.maturity_date'],
    'metric.debt_to_ebitda': ['financial.total_debt', 'financial.ebitda'],
    'metric.dscr': ['financial.net_operating_income', 'financial.debt_service'],
    'metric.interest_coverage': ['financial.ebit', 'financial.interest_expense'],
    'metric.ltv_percent': ['facility.requested_amount', 'collateral.valuation_amount'],
    'collateral.eligible_value': ['collateral.valuation_amount', 'collateral.haircut_percent'],
}


def canonical_name(field):
    return ALIASES.get(field, field if '.' in field else 'requirement.' + field)


def provenance_sources(provenance):
    sources={provenance['source_type']}
    for item in provenance.get('inputs',[]): sources.update(provenance_sources(item))
    return sources


def field_spec(name):
    if name in ('collateral.is_secured','approval.ltv_exception_applies','regulatory.stricter_local_ltv_applies'):return 'boolean',None
    if name in ('risk.breach_trigger','risk.warning_trigger'): return 'boolean', None
    if name.startswith('documentation.'): return 'object', None
    if name == 'facility.tenor_months': return 'integer', 'months'
    if name.endswith(('_date', 'period_end')): return 'date', None
    if name.endswith(('_percent', 'ltv_percent')): return 'number', '%'
    if name.startswith('metric.'): return 'number', 'x'
    if name.startswith(('financial.', 'exposure.')) or name.endswith(('_amount', 'eligible_value')): return 'number', 'currency'
    if name == 'documentation.documents': return 'object', None
    if name in ALIASES.values(): return 'string', None
    return 'unknown', None


def condition_fields(condition):
    if not condition: return set()
    fields = {condition['field']} if condition.get('field') else set()
    for key in ('all', 'any'):
        for child in condition.get(key) or []: fields.update(condition_fields(child))
    return fields


def derive_registry(rules):
    registry, mappings = {}, []
    for rule in rules:
        d = rule['definition']; logic = d.get('calculation_logic') or {}
        applicability = condition_fields(d.get('applicability_conditions'))
        applicability |= condition_fields(d.get('applicability_exclusions'))
        if d.get('applicable_stage'): applicability.add('status')
        calculation = {logic[k] for k in ('field', 'numerator', 'denominator', 'as_of_field') if logic.get(k)} | condition_fields(logic.get('condition'))
        fields = set(referenced_fields(d))
        fields.update(e['key'] for e in d.get('evidence_requirements', []))
        evidence_names = {e['key']: 'documentation.'+e['key'] for e in d.get('evidence_requirements',[]) if e.get('type') in ('document','approval')}
        names = {field:evidence_names.get(field,canonical_name(field)) for field in fields}
        metadata = {m['field_name']: m for m in d.get('input_field_definitions') or []}
        evidence_metadata = {e['key']:e for e in d.get('evidence_requirements',[])}
        for field in fields:
            name = names[field]; dtype, unit = field_spec(name); meta = dict(metadata.get(field, {}))
            meta['definition'] = meta.get('definition') or evidence_metadata.get(field,{}).get('description')
            if dtype=='unknown' and field in {logic.get('numerator'),logic.get('denominator')}: dtype='number'
            if dtype=='unknown' and field==logic.get('field') and isinstance(d.get('threshold_value'),(int,float)): dtype='number'; unit=d.get('threshold_unit')
            entry = registry.setdefault(name, {
                'canonical_field_name': name, 'business_name': name.split('.')[-1].replace('_', ' ').title(),
                'business_definition': ('Observed '+name.replace('.', ' ').replace('_',' ')+'.') if name in ALIASES.values() else None, 'data_type': dtype, 'unit': unit, 'allowed_values': [],
                'required': False, 'domain': name.split('.')[0], 'aliases': [], 'source_rule_ids': [],
                'applicable_policy_ids': [], 'expected_sources': [], 'calculation_method': DERIVATIONS.get(name),
                'temporal_requirement': 'Explicit as-of date; reporting period/entity selected at resolution',
                'evidence_requirements': [], 'validation_rules': ['Finite numeric values', 'Explicit source and entity/period identity'],
                'metadata_status': 'MAPPED' if name in ALIASES.values() or field in evidence_names else 'REQUIRES_DEFINITION',
                'source_definitions': [], 'source_units': [],
            })
            entry['required'] |= meta.get('required', True)
            if field not in entry['aliases']: entry['aliases'].append(field)
            if rule['id'] not in entry['source_rule_ids']: entry['source_rule_ids'].append(rule['id'])
            if rule['policy_id'] not in entry['applicable_policy_ids']: entry['applicable_policy_ids'].append(rule['policy_id'])
            if meta.get('definition'):
                entry['business_definition'] = entry['business_definition'] or meta['definition']
                if meta['definition'] not in entry['source_definitions']: entry['source_definitions'].append(meta['definition'])
            if meta.get('unit') and meta['unit'] not in entry['source_units']: entry['source_units'].append(meta['unit'])
            for source in ([d['data_source']] if d.get('data_source') else []) + (d.get('data_sources') or []):
                if source not in entry['expected_sources']: entry['expected_sources'].append(source)
            for evidence in d.get('evidence_requirements', []):
                if evidence not in entry['evidence_requirements']: entry['evidence_requirements'].append(evidence)
            entry.setdefault('workflow_stages', [])
            if d.get('applicable_stage') and d['applicable_stage'] not in entry['workflow_stages']: entry['workflow_stages'].append(d['applicable_stage'])
        mappings.append({'rule_id': rule['id'], 'policy_id': rule['policy_id'], 'rule_name': d['rule_name'],
                         'required_fields': sorted(set(names.values())),
                         'field_map': {f: names[f] for f in sorted(fields)},
                         'applicability_fields': sorted({canonical_name(f) for f in applicability}),
                         'calculation_inputs': sorted({canonical_name(f) for f in calculation}),
                         'actual_field': canonical_name(logic['field']) if logic.get('field') else None,
                         'raw_or_derived': logic.get('method'), 'evidence': d.get('evidence_requirements', []),
                         'missing_behavior': 'Unable to Assess; no generated replacement'})
    # Register dependency inputs even when the rule refers only to the derived value.
    for name in list(registry):
        for dep in DERIVATIONS.get(name, []):
            if dep not in registry:
                dtype, unit = field_spec(dep)
                registry[dep] = {**deepcopy(registry[name]), 'canonical_field_name': dep, 'business_name': dep.split('.')[-1].replace('_', ' ').title(),
                                 'business_definition': 'Observed '+dep.replace('.',' ').replace('_',' ')+', required as a calculation input.',
                                 'data_type': dtype, 'unit': unit, 'domain': dep.split('.')[0], 'aliases': [], 'calculation_method': None,
                                 'source_definitions': [], 'source_units': [], 'metadata_status':'MAPPED'}
    for attribute in registry.values():
        attribute['metadata_gaps']=[key for key in ('business_definition','expected_sources') if not attribute.get(key)]
        if attribute['data_type']=='unknown': attribute['metadata_gaps'].append('data_type')
    return list(registry.values()), mappings


def create_tables(c):
    c.execute('''CREATE TABLE IF NOT EXISTS credit_data.credit_data_attributes (
        canonical_field_name TEXT PRIMARY KEY, definition JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
    c.execute('''CREATE TABLE IF NOT EXISTS credit_data.rule_credit_data_mappings (
        rule_version_id BIGINT PRIMARY KEY, definition JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
    c.execute('''CREATE TABLE IF NOT EXISTS "user".credit_data_records (
        user_id TEXT NOT NULL DEFAULT NULLIF(current_setting('app.user_id',true),''),
        request_id TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
        data JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(user_id,request_id))''')


def sync_registry(rules):
    from ..database import shared_policy_connection
    attributes, mappings = derive_registry(rules)
    with shared_policy_connection() as c:
        for attribute in attributes:
            c.execute('''INSERT INTO credit_data_attributes VALUES (%s,%s::jsonb,now())
                ON CONFLICT(canonical_field_name) DO UPDATE SET definition=excluded.definition,updated_at=now()''',
                      (attribute['canonical_field_name'], json.dumps(attribute)))
        for mapping in mappings:
            c.execute('''INSERT INTO rule_credit_data_mappings VALUES (%s,%s::jsonb,now())
                ON CONFLICT(rule_version_id) DO UPDATE SET definition=excluded.definition,updated_at=now()''',
                      (mapping['rule_id'], json.dumps(mapping)))
    return attributes, mappings


def fact(request_id, name, value, unit=None, source_type='SYNTHETIC', as_of=None, **source):
    now = datetime.now(timezone.utc).isoformat()
    if source_type not in SOURCE_TYPES: raise ValueError('Unsupported source type')
    return {'value': value, 'unit': unit, 'as_of_date': as_of or date.today().isoformat(),
            'provenance': {'request_id': request_id, 'attribute_name': name, 'value': value, 'unit': unit,
                           'source_type': source_type, 'source_identifier': 'credit-data-generator-v1' if source_type == 'SYNTHETIC' else None,
                           'source_document_id': None, 'source_page': None, 'source_section': None, 'source_reference': None,
                           'extraction_method': 'deterministic manufacture' if source_type == 'SYNTHETIC' else 'supplied',
                           'confidence': None, 'extracted_at': now, 'model_version': None, 'verified_by': None,
                           'verification_status': 'MANUFACTURED' if source_type == 'SYNTHETIC' else 'UNVERIFIED',
                           'last_updated_at': now, **source}}


def tenor_months(start, maturity):
    start, maturity = date.fromisoformat(str(start)), date.fromisoformat(str(maturity))
    if maturity < start: raise ValueError('Maturity precedes start')
    # Whole contractual calendar months; partial month remains a fraction for comparison.
    months = (maturity.year-start.year)*12 + maturity.month-start.month
    anchor_day = min(start.day, calendar.monthrange(maturity.year, maturity.month)[1])
    return months + (maturity.day-anchor_day)/calendar.monthrange(maturity.year, maturity.month)[1]


def normalize_unit(value, source, target):
    source, target = (source or '').lower().strip(), (target or '').lower().strip()
    if source == target or not target: return value
    groups = [{'months': Decimal(1), 'month': Decimal(1), 'years': Decimal(12), 'year': Decimal(12)},
              {'%': Decimal('.01'), 'percent': Decimal('.01'), 'percentage':Decimal('.01'), 'bps':Decimal('.0001'), 'basis points':Decimal('.0001'), 'x': Decimal(1), 'ratio': Decimal(1)}]
    for units in groups:
        if source in units and target in units: return float(Decimal(str(value))*units[source]/units[target])
    currencies = r'(usd|inr|eur|gbp|jpy|cad|aud|chf|cny|aed|sgd|hkd)'
    left, right = re.search(currencies, source), re.search(currencies, target)
    if left and right and left[0] == right[0]:
        def scale(unit):
            return next((Decimal(n) for word, n in [('billion', 10**9), ('million', 10**6), ('thousand', 10**3)] if word in unit), Decimal(1))
        return float(Decimal(str(value))*scale(source)/scale(target))
    raise ValueError(f'Incompatible units: {source} / {target}')


def select_entity(record, domain, entity_id=None, period=None):
    entities = record.get('entities', {}).get(domain, [])
    if entity_id is not None: entities = [e for e in entities if e['entity_id'] == entity_id]
    if period is not None: entities = [e for e in entities if e.get('period_end') == period]
    if len(entities) != 1: return None  # Never choose an arbitrary facility or reporting period.
    return entities[0]


def read_fact(record, name, entity_id=None, period=None):
    domain, key = name.split('.', 1)
    entity = select_entity(record, domain, entity_id, period)
    stored = entity.get('attributes', {}).get(key) if entity else None
    if not entity and name not in DERIVATIONS: return None
    if name not in DERIVATIONS: return deepcopy(stored)
    deps = DERIVATIONS[name]
    inputs = [read_fact(record, dep, entity_id if dep.startswith('facility.') else None, period if dep.startswith('financial.') else None) for dep in deps]
    if any(v is None or v.get('value') is None for v in inputs): return None
    if len({v.get('as_of_date') for v in inputs}) > 1: return None
    try:
        values = [v['value'] for v in inputs]
        if name == 'facility.tenor_months': value = math.ceil(tenor_months(*values))
        else:
            if name != 'collateral.eligible_value' and inputs[0].get('unit') != inputs[1].get('unit'): return None
            a, b = map(lambda v: Decimal(str(v)), values)
            if name == 'collateral.eligible_value': value = float(a*(1-b/100))
            else:
                if b == 0: return None
                value = float(a/b*(100 if name == 'metric.ltv_percent' else 1))
        derived = fact(record['request_id'], name, value, field_spec(name)[1], 'DERIVED', inputs[0]['as_of_date'],
                       source_identifier='canonical-calculations-v1', extraction_method='deterministic calculation',
                       inputs=[v['provenance'] for v in inputs], verification_status='CALCULATED')
        if stored and Decimal(str(stored['value'])) != Decimal(str(value)):
            derived['conflicting'] = True
            derived['alternative'] = stored
        return derived
    except (ValueError, TypeError, ArithmeticError): return None


def resolve_actual(rule, record, *, entity_id=None, period=None, as_of=None, taxonomy_normalization=()):
    d = rule.get('definition', rule); request_id = record['request_id']; as_of = as_of or date.today()
    _, mappings = derive_registry([{'id': rule.get('id', 0), 'policy_id': rule.get('policy_id', 0), 'definition': d}])
    mapping = mappings[0]; data, resolved, missing, provenance, conflicts = {}, [], [], [], []
    facility_dependent = any(name.startswith('facility.') or any(dep.startswith('facility.') for dep in DERIVATIONS.get(name,[])) for name in mapping['required_fields'])
    facilities = record.get('entities',{}).get('facility',[])
    if entity_id is None and facility_dependent and len(facilities)>1:
        instances = [{**resolve_actual(rule,record,entity_id=e['entity_id'],period=period,as_of=as_of,taxonomy_normalization=taxonomy_normalization),'entity_id':e['entity_id']} for e in facilities]
        relevant = [r for r in instances if r['evaluation']['result']!='Not Applicable']
        rank = {'Breach':6,'Warning':5,'Manual Review Required':4,'Unable to Assess':3,'Pass':2,'Not Applicable':1}
        worst = max(relevant or instances,key=lambda r:rank[r['evaluation']['result']])
        evaluation=deepcopy(worst['evaluation'])
        evaluation['observed_value']=[{'entity_id':r['entity_id'],'value':r['actual_value'],'result':r['evaluation']['result']} for r in relevant]
        evaluation['input_values']={r['entity_id']:r['evaluation']['input_values'] for r in instances}
        evaluation['missing_inputs']=sorted({f for r in relevant for f in r['evaluation']['missing_inputs']})
        evaluation['variance']=None
        evaluation['applicability_reason']='Evaluated each facility separately; '+evaluation['applicability_reason']
        statuses={r['resolution_status'] for r in relevant}
        status='CONFLICTING' if 'CONFLICTING' in statuses else 'PARTIAL' if statuses & {'PARTIAL','MISSING'} else 'COMPLETE'
        return {**{k:v for k,v in worst.items() if k not in ('evaluation','engine_data','entity_id')},
                'evaluation':evaluation,'actual_value':evaluation['observed_value'],'instances':instances,
                'resolved_fields':[{**f,'entity_id':r['entity_id']} for r in relevant for f in r['resolved_fields']],
                'missing_fields':sorted({f for r in relevant for f in r['missing_fields']}),
                'provenance':[p for r in relevant for p in r['provenance']],
                'actual_provenance':{'source_type':'DERIVED','attribute_name':'assessment.observed_value','value':evaluation['observed_value'],
                                     'source_identifier':'all-facility-assessment','inputs':[r['actual_provenance'] for r in relevant if r.get('actual_provenance')]},
                'resolution_status':status,'engine_data':{'evidence':record.get('evidence',[])}}
    for alias, name in mapping['field_map'].items():
        item = read_fact(record, name, entity_id if name.startswith(('facility.', 'metric.')) else None, period if name.startswith(('financial.', 'metric.')) else None)
        if not item or item.get('value') is None:
            missing.append(name); continue
        try:
            dtype, _ = field_spec(name); value = item['value']
            if dtype in ('number', 'integer'):
                if isinstance(value, bool) or not Decimal(str(value)).is_finite(): raise ValueError('Invalid number')
                if dtype=='integer' and Decimal(str(value)) != Decimal(str(value)).to_integral_value(): raise ValueError('Invalid integer')
            if dtype == 'date': date.fromisoformat(str(value))
            if dtype == 'string' and not isinstance(value, str): raise ValueError('Invalid string')
            if dtype == 'boolean' and not isinstance(value, bool): raise ValueError('Invalid boolean')
            if dtype == 'object' and not isinstance(value,(dict,list)): raise ValueError('Invalid structured value')
            observed_date = date.fromisoformat(item['as_of_date'])
            if observed_date > as_of: raise ValueError('Future data')
            max_age = d.get('data_freshness_days')
            if max_age is not None and (as_of-observed_date).days > max_age: raise ValueError('Stale data')
            # Existing engine scales monetary magnitudes; it must receive base-currency facts.
            logic = d.get('calculation_logic') or {}
            target = item.get('unit')
            if logic.get('method') == 'direct' and logic.get('field') == alias:
                target = d.get('threshold_unit') or target
                currency = re.search(r'\b(USD|INR|EUR|GBP|JPY|CAD|AUD|CHF|CNY|AED|SGD|HKD)\b', target or '')
                if currency: target = currency[0]
            value = normalize_unit(value, item.get('unit'), target)
            node = data
            keys = alias.split('.')
            for key in keys[:-1]: node = node.setdefault(key, {})
            node[keys[-1]] = value
            resolved.append({'attribute_name': name, 'rule_field': alias, **item, 'normalized_value': value, 'normalized_unit': target})
            provenance.append(item['provenance'])
            if item.get('conflicting') or item.get('provenance', {}).get('verification_status') == 'CONFLICTING' or any(a.get('value') != item['value'] for a in item.get('alternatives', [])): conflicts.append(name)
        except (ValueError, TypeError, ArithmeticError, KeyError): missing.append(name)
    evidence = deepcopy(record.get('evidence', []))
    for requirement in d.get('evidence_requirements', []):
        item = next((f for f in resolved if f['rule_field']==requirement['key']),None)
        if item and requirement['type'] in ('document','approval') and isinstance(item['value'],dict) and item['value'].get('present') is True:
            evidence.append({'key':requirement['key'],'value':item['value'], 'source':item['provenance']['source_type'],
                             'reference':item['value'].get('document_id'),'provenance':item['provenance']})
    data['evidence'] = evidence
    if taxonomy_normalization:
        from ..risk_knowledge.taxonomy import apply_normalization
        data = apply_normalization(data, taxonomy_normalization)
    status = 'CONFLICTING' if conflicts else 'PARTIAL' if missing and resolved else 'MISSING' if missing else 'COMPLETE'
    evaluation = execute_rule(d, data, as_of)
    logic = d.get('calculation_logic') or {}
    if logic.get('method') in ('ratio','percentage'):
        by_alias = {f['rule_field']: f for f in resolved}
        left, right = by_alias.get(logic.get('numerator')), by_alias.get(logic.get('denominator'))
        if left and right and left['unit'] != right['unit']:
            missing.append('Compatible calculation input units')
            status = 'PARTIAL'
    if conflicts: evaluation.update(result='Manual Review Required', severity=None, missing_inputs=['Conflicting data: '+', '.join(conflicts)])
    elif missing and evaluation['result'] not in ('Not Applicable', 'Manual Review Required'):
        evaluation.update(result='Unable to Assess', severity=None, missing_inputs=sorted(set(missing+evaluation['missing_inputs'])))
    actual_unit = d.get('threshold_unit') or ('x' if logic.get('method')=='ratio' else '%' if logic.get('method')=='percentage' else 'days' if logic.get('method')=='date_age' else None)
    actual_provenance = None
    if evaluation['observed_value'] is not None:
        actual_provenance = fact(request_id,'assessment.observed_value',evaluation['observed_value'],actual_unit,'DERIVED',
                                 as_of.isoformat(),source_identifier='policy-rule-engine:'+str(rule.get('id')),
                                 extraction_method='deterministic evaluation',inputs=deepcopy(provenance),
                                 verification_status='CALCULATED')['provenance']
    return {'rule_id': rule.get('id'), 'request_id': request_id, 'required_fields': mapping['required_fields'],
            'resolved_fields': resolved, 'missing_fields': sorted(set(missing)), 'actual_value': evaluation['observed_value'],
            'unit': actual_unit, 'provenance': provenance, 'actual_provenance':actual_provenance, 'evidence': evidence, 'resolution_status': status,
            'evaluation': evaluation, 'engine_data': data}


def load_record(request_id, *, connection=None):
    from contextlib import nullcontext
    from ..database import db_connection
    from ..data_encryption import decode_record
    with (db_connection() if connection is None else nullcontext(connection)) as c:
        row = c.execute('SELECT data,revision FROM credit_data_records WHERE request_id=%s', (request_id,)).fetchone()
    return {**decode_record(row['data']), 'revision': row['revision']} if row else None


def project_record(record):
    """Compatibility projection for existing policy scope/applicability services."""
    data = {'evidence': deepcopy(record.get('evidence', [])), 'data_source': 'Canonical Credit Request Data'}
    data['credit_request_number']=record['request_id']; data['request_id']=record['request_id']
    for alias, name in ALIASES.items():
        item = read_fact(record, name)
        if item and item['value'] is not None and not item.get('conflicting'):
            value = item['value']
            if name == 'facility.tenor_months' and alias in ('term_loan_tenor','revolving_credit_tenor','trade_finance_tenor','recommended_tenor_years'): value /= 12
            data[alias] = value
    return data


def validate_record(record):
    if not isinstance(record.get('request_id'), str) or not isinstance(record.get('entities'), dict): raise ValueError('Request ID and entities required')
    for domain, entities in record['entities'].items():
        if not isinstance(entities, list):
            raise ValueError('Entity groups must be lists')
        ids = set()
        for entity in entities:
            if not isinstance(entity, dict) or not isinstance(entity.get('attributes'), dict):
                raise ValueError('Entity attributes must be an object')
            identity = (entity['entity_id'], entity.get('period_end'))
            if identity in ids: raise ValueError('Duplicate entity/period')
            ids.add(identity)
            for key, item in entity['attributes'].items():
                if not isinstance(item, dict) or not isinstance(item.get('provenance'), dict):
                    raise ValueError('Attribute provenance must be an object')
                p = item['provenance']; name = domain+'.'+key
                required_provenance = {'request_id','attribute_name','value','unit','source_type','source_identifier',
                                       'source_document_id','source_page','source_section','source_reference','extraction_method',
                                       'confidence','extracted_at','model_version','verified_by','verification_status','last_updated_at'}
                if not required_provenance <= p.keys(): raise ValueError('Incomplete provenance')
                if p['source_type'] not in SOURCE_TYPES or p['request_id'] != record['request_id'] or p['attribute_name'] != name: raise ValueError('Invalid provenance identity')
                if p['value'] != item['value'] or p.get('unit') != item.get('unit'): raise ValueError('Provenance value mismatch')
                if p['source_type'] != 'SYNTHETIC' and not p.get('source_identifier'): raise ValueError('Source reference required')
                if p['source_type']=='DOCUMENT_EXTRACTED' and not p.get('source_document_id'): raise ValueError('Document identity required')
                if p['source_type']=='SYNTHETIC' and p['verification_status']!='MANUFACTURED': raise ValueError('Synthetic data must be labelled manufactured')
                if p['confidence'] is not None and (isinstance(p['confidence'],bool) or not 0 <= float(p['confidence']) <= 1): raise ValueError('Invalid confidence')
                datetime.fromisoformat(p['extracted_at']); datetime.fromisoformat(p['last_updated_at'])
                date.fromisoformat(item['as_of_date'])
                dtype, _ = field_spec(name)
                if item['value'] is not None and dtype in ('number', 'integer'):
                    try:
                        number = Decimal(str(item['value']))
                    except InvalidOperation as error:
                        raise ValueError('Invalid number') from error
                    if not number.is_finite(): raise ValueError('Invalid number')
                    if dtype == 'integer' and number != number.to_integral_value(): raise ValueError('Invalid integer')
                if item['value'] is not None and dtype=='string' and not isinstance(item['value'],str): raise ValueError('Invalid string')
                if item['value'] is not None and dtype=='boolean' and not isinstance(item['value'],bool): raise ValueError('Invalid boolean')
                if item['value'] is not None and dtype=='object' and not isinstance(item['value'],(dict,list)): raise ValueError('Invalid structured value')
    return record


class CreditDataRevisionConflict(ValueError):
    pass


def store_record(record, expected_revision=None, *, connection=None):
    from contextlib import nullcontext
    from ..database import db_connection
    from ..data_encryption import decode_record, encode_record
    validate_record(record)
    encoded = encode_record(record)
    with (nullcontext(connection) if connection is not None else db_connection()) as c:
        current = c.execute('SELECT revision FROM credit_data_records WHERE request_id=%s FOR UPDATE', (record['request_id'],)).fetchone()
        if expected_revision is not None and (current['revision'] if current else 0) != expected_revision:
            raise CreditDataRevisionConflict('Credit data revision changed')
        saved=c.execute('''INSERT INTO credit_data_records(request_id,data) VALUES (%s,%s::jsonb)
            ON CONFLICT(user_id,request_id) DO UPDATE SET data=excluded.data,revision=credit_data_records.revision+1,updated_at=now()
            WHERE %s::integer IS NULL OR credit_data_records.revision=%s RETURNING data,revision''',
                  (record['request_id'], encoded, expected_revision, expected_revision)).fetchone()
        if saved is None:
            raise CreditDataRevisionConflict('Credit data revision changed')
        return {**decode_record(saved['data']), 'revision': saved['revision']}


def synthetic_record(proposal, rules, scenario='compliant', as_of=None):
    """Manufacture before assessment. No invented thresholds or arbitrary documentary claims."""
    if scenario not in {'compliant', 'boundary', 'near_threshold', 'warning', 'breach', 'multiple_breaches', 'missing', 'conflicting'}: raise ValueError('Unknown scenario')
    as_of = as_of or date.today(); request_id = proposal['credit_request_number']
    record = {'schema_version': 1, 'request_id': request_id, 'entities': {}, 'evidence': [], 'scenario': scenario}
    currency = proposal.get('currency', 'USD')
    def put(name, value, unit=None, entity_id='primary', period=None):
        domain, key = name.split('.', 1)
        entities = record['entities'].setdefault(domain, [])
        entity = next((e for e in entities if e['entity_id'] == entity_id and e.get('period_end') == period), None)
        if entity is None:
            entity = {'entity_id': entity_id, 'period_end': period, 'attributes': {}}; entities.append(entity)
        entity['attributes'][key] = fact(request_id, name, value, unit, as_of=as_of.isoformat())
    # Reuse existing request facts; explicitly retain their manufactured origin.
    for alias, value in proposal.items():
        if alias in ALIASES and value is not None and canonical_name(alias) not in DERIVATIONS:
            name = canonical_name(alias); dtype, unit = field_spec(name)
            put(name, float(value) if dtype == 'number' else value, currency if unit == 'currency' else unit)
    put('credit_request.currency', currency)
    put('borrower.external_rating', proposal.get('rating', 'BBB'))
    put('borrower.rating_evidence', 'synthetic-rating-report:'+request_id)
    put('facility.requested_amount', float(proposal['requested_amount']), currency)
    debt = float(proposal.get('exposure', 0)) + float(proposal['requested_amount'])
    values = {'total_debt': debt, 'ebitda': debt/3.5, 'ebit': debt/4, 'net_operating_income': debt/3.5,
              'debt_service': debt/3.5/1.6, 'interest_expense': debt/10,
              'senior_debt': debt*.8, 'total_debt_including_mezzanine': debt}
    for name, value in values.items(): put('financial.'+name, value, currency)
    put('collateral.valuation_amount', debt/.65, currency)
    put('collateral.haircut_percent', 20, '%')
    put('collateral.valuation_date', as_of.isoformat())
    months = int(float(proposal.get('recommended_tenor_years') or 3)*12)
    adjusted = set()
    priority = 'WARNING' if scenario == 'warning' else 'BREACH' if scenario in ('breach','multiple_breaches') else None
    scenario_rules = sorted(rules, key=lambda r: 0 if priority and r['definition'].get('severity') == priority else 1)
    for rule in scenario_rules:
        d = rule['definition']; logic = d.get('calculation_logic') or {}; threshold = d.get('threshold_value'); op = d.get('operator')
        if op == 'between' and isinstance(d.get('upper_bound'), (int,float)): threshold = d['upper_bound']
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or threshold <= 0 or op not in ('between','less_than','less_than_or_equal','greater_than','greater_than_or_equal'): continue
        method = logic.get('method'); target = canonical_name(logic.get('field') or logic.get('numerator') or '')
        if target in adjusted: continue  # One coherent actual shared across policies, never per-rule overrides.
        upper = op.startswith('less') or op == 'between'; fail = scenario in ('warning', 'breach', 'multiple_breaches')
        factor = 1 if scenario == 'boundary' else (.98 if upper else 1.02) if scenario == 'near_threshold' else 1.2 if upper == fail else .8
        desired = float(threshold)*factor
        if method == 'direct' and target == 'facility.tenor_months':
            field = logic.get('field','')
            facility = str(proposal.get('facility','')).lower()
            if field == 'term_loan_tenor' and facility not in ('term loan', 'term_loan'): continue
            if field == 'revolving_credit_tenor' and facility not in ('revolver','revolving credit','revolving credit facility'): continue
            if field == 'trade_finance_tenor' and 'trade' not in facility: continue
            months = max(1, round(normalize_unit(desired, d.get('threshold_unit'), 'months'))); adjusted.add(target)
        elif method in ('ratio', 'percentage'):
            denominator = canonical_name(logic.get('denominator') or '')
            # Change independent financial/collateral inputs, never policy limits or portfolio totals.
            if target.startswith('financial.') and denominator in ('financial.ebitda', 'financial.debt_service', 'financial.interest_expense'):
                numerator = read_fact(record, target)
                if numerator:
                    ratio = desired/100 if method == 'percentage' or d.get('threshold_unit') in ('%', 'percent') else desired
                    put(denominator, numerator['value']/ratio, currency); adjusted.add(target); adjusted.add(denominator)
            elif denominator == 'collateral.valuation_amount' and target == 'facility.requested_amount':
                ratio = desired/100 if method == 'percentage' or d.get('threshold_unit') in ('%', 'percent') else desired
                put(denominator, float(proposal['requested_amount'])/ratio, currency); adjusted.add(target)
        if scenario in ('breach','warning') and adjusted: break
    put('facility.start_date', as_of.replace(day=1).isoformat())
    month_index = as_of.year*12 + as_of.month-1 + months
    put('facility.maturity_date', date(month_index//12, month_index%12+1, 1).isoformat())
    if scenario == 'missing': record['entities'].pop('financial', None); record['entities']['facility'][0]['attributes'].pop('maturity_date', None)
    if scenario == 'conflicting': put('facility.tenor_months', months+12, 'months')
    # Explicit manufactured supporting data, not an assertion of bank verification.
    from .rule_engine import calculate, compare
    projected = project_record(record)
    triggers = {'BREACH': False, 'WARNING': False}
    for rule in rules:
        d=rule['definition']; logic=d.get('calculation_logic') or {}
        if d.get('severity') not in triggers or logic.get('method') not in ('ratio','percentage','direct'): continue
        threshold = [d.get('lower_bound'),d.get('upper_bound')] if d.get('operator')=='between' else d.get('threshold_value')
        try:
            actual,missing,_=calculate(logic,projected,as_of)
            if not missing and actual is not MISSING and compare(actual,d['operator'],threshold): triggers[d['severity']]=True
        except (ValueError,TypeError,ArithmeticError,KeyError): continue
    put('risk.breach_trigger', triggers['BREACH']); put('risk.warning_trigger', triggers['WARNING'])
    for document in ('remediation_plan','corrective_action_plan'):
        name='documentation.'+document
        put(name, {'document_id':'synthetic:'+request_id+':'+document, 'present':True,
                   'description':'Manufactured Demonstration Data: illustrative monitoring and remediation plan.'})
        record['evidence'].append({'key':document,'source':'SYNTHETIC','source_type':'SYNTHETIC',
                                  'reference':'synthetic:'+request_id+':'+document,
                                  'value':'Manufactured Demonstration Data: illustrative monitoring and remediation plan.'})
    return validate_record(record)


def coverage_report(rules, record):
    rows = []; counts = {'fully_evaluable': 0, 'partially_supported': 0, 'lacking_actual_data': 0, 'manual_documentary': 0}
    for rule in rules:
        resolved = resolve_actual(rule, record); evaluation = resolved['evaluation']
        executable = evaluation['result'] in ('Pass', 'Warning', 'Breach')
        manual = evaluation['result'] == 'Manual Review Required'
        category = 'fully_evaluable' if executable else 'manual_documentary' if manual else 'partially_supported' if resolved['resolved_fields'] else 'lacking_actual_data'
        counts[category] += 1
        rows.append({'rule_id': rule['id'], 'rule_name': rule['definition']['rule_name'], 'policy_id': rule['policy_id'],
                     'policy': rule.get('title'), 'required_fields': resolved['required_fields'],
                     'available_fields': sorted({f['attribute_name'] for f in resolved['resolved_fields']}),
                     'missing_fields': resolved['missing_fields'], 'derived_fields': [p['attribute_name'] for p in resolved['provenance'] if p['source_type']=='DERIVED'],
                     'evidence_available': [e for e in resolved['evidence'] if e.get('key') in {req['key'] for req in rule['definition'].get('evidence_requirements',[])}], 'data_sources': sorted({p['source_type'] for p in resolved['provenance']}),
                     'executable': executable, 'result': evaluation['result'], 'category': category,
                     'reason': None if executable else '; '.join(evaluation['missing_inputs']) or evaluation['result']})
    return {'request_id': record['request_id'], 'revision': record.get('revision'), 'counts': counts, 'rules': rows}
