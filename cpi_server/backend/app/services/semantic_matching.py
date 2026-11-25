"""Deterministic request matching over the current source-backed semantic graph.

No LLM selects rules or supplies missing scope. Policy containment, applicability,
conditions and exception inheritance are traversed from graph relationships.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from ..risk_knowledge.semantic_extraction import assemble_graph, digest
from ..risk_knowledge.policy_taxonomy import FACETS
from ..risk_knowledge.competency_projection import ORDERED_RATING_FIELDS, RATINGS
from .credit_data import ALIASES, GROUPS, DERIVATIONS, read_fact
from .rule_engine import field_value, MISSING

VERSION = 'semantic-graph-matching-v2'
STATUS = {True: 'Applicable', False: 'Not Applicable', None: 'Unable to Determine'}
RELATIVE_JURISDICTIONS = ('home jurisdiction', 'foreign jurisdiction')
FIELD_ALIASES = {
    'product': ('product', 'facility', 'facility_type', 'facility.facility_type'),
    'customer_segment': ('customer_segment', 'segment', 'borrower.customer_segment'),
    'geography': ('geography', 'country', 'borrower.geography'),
    'loan_amount': ('loan_amount', 'requested_amount', 'credit_request.requested_amount'),
    'credit_score': ('credit_score', 'bureau_score'),
    'dti': ('dti', 'dti_ratio', 'debt_to_income'),
    'interest_coverage_ratio': ('icr', 'interest_coverage_ratio'),
    'total_debt_to_ebitda': ('debt_to_ebitda', 'leverage_ratio'),
    'tenor': ('tenor_months', 'facility_tenor_months'),
    'business_line': ('business_line','policy_area'),
}
KNOWN_UNITS = {'ltv': '%', 'ltv_ratio': '%', 'loan_to_value': '%', 'dti': '%', 'dti_ratio': '%',
    'dscr': 'x', 'debt_service_coverage_ratio': 'x', 'icr': 'x', 'interest_coverage_ratio': 'x',
    'debt_to_ebitda': 'x', 'leverage_ratio': 'x', 'credit_score': 'score', 'bureau_score': 'score',
    'tenor_months': 'months', 'facility_tenor_months': 'months'}
GEOGRAPHY_ALIASES={'us':'united states','usa':'united states','uk':'united kingdom','gb':'united kingdom',
                   'gbr':'united kingdom','in':'india','ind':'india','sg':'singapore','sgp':'singapore','eu':'european union'}


def normalized(value, facet=None):
    text = re.sub(r'\s+', ' ', str(value).strip().casefold())
    if facet=='geography':text=GEOGRAPHY_ALIASES.get(text,text)
    for name, aliases in FACETS.get(facet, []):
        if text in {name.casefold(), *(a.casefold() for a in aliases)}:
            return name.casefold()
    return text


def number(value):
    if isinstance(value, bool): raise ValueError('Boolean is not a numeric fact')
    n = Decimal(str(value))
    if not n.is_finite(): raise ValueError('Non-finite fact')
    return n


def unit_spec(unit):
    text = normalized(unit or '')
    if text in ('%', 'percent', 'percentage', 'percentage points'): return 'percent', Decimal(1), None
    if text in ('x', 'ratio', 'times', 'multiple'): return 'ratio', Decimal(1), None
    if text in ('score', 'points', 'point'): return 'score', Decimal(1), None
    if text in ('month', 'months'): return 'months', Decimal(1), None
    if text in ('year', 'years'): return 'months', Decimal(12), None
    if text in ('day', 'days'): return 'days', Decimal(1), None
    currency = re.search(r'\b(usd|inr|eur|gbp|jpy|cad|aud|chf|cny|aed|sgd|hkd)\b', text)
    scales = {'thousand': 1000, 'thousands': 1000, 'lakh': 100000, 'lakhs': 100000,
              'million': 1000000, 'millions': 1000000, 'crore': 10000000, 'crores': 10000000,
              'billion': 1000000000, 'billions': 1000000000}
    scale = next((v for k, v in scales.items() if re.search(r'\b'+k+r'\b', text)), 1)
    if currency or scale != 1 or text in ('currency', 'amount'):
        return 'money', Decimal(scale), currency[1] if currency else None
    return text, Decimal(1), None


def converted(actual, source_unit, target_unit):
    if not target_unit: return actual
    source, sf, sc = unit_spec(source_unit)
    target, tf, tc = unit_spec(target_unit)
    if not source or source != target or (tc and sc != tc):
        raise ValueError('Missing or incompatible units/currency')
    return number(actual)*sf/tf


class Facts:
    def __init__(self, proposal):
        self.data = proposal

    def get(self, field):
        names = FIELD_ALIASES.get(field, (field,))
        canonical = next((ALIASES.get(n, n if n in GROUPS else None) for n in names if ALIASES.get(n) or n in GROUPS), None)
        record = self.data.get('_canonical_record')
        if record and canonical:
            item = read_fact(record, canonical)
            # A supplied metric remains usable when calculation inputs are
            # absent. Do not replace an existing stored observation.
            if item is None:
                domain,key=canonical.split('.',1)
                entities=record.get('entities',{}).get(domain,[])
                if len(entities)==1:item=entities[0].get('attributes',{}).get(key)
            if not item or item.get('value') is None:
                domains={n.split('.')[0] for n in [canonical,*DERIVATIONS.get(canonical,[])]}
                ambiguous=any(len(record.get('entities',{}).get(d,[]))>1 for d in domains)
                return None,None,{'field':field,'status':'AMBIGUOUS_CANONICAL_FACT' if ambiguous else 'MISSING_CANONICAL_FACT'}
            if (item.get('conflicting') or item.get('provenance',{}).get('verification_status')=='CONFLICTING' or
                (item.get('as_of_date') and str(item['as_of_date'])[:10] > date.today().isoformat())):
                return None, None, {'field': field, 'status': 'CONFLICTING_OR_FUTURE_CANONICAL_FACT'}
            return item['value'], item.get('unit'), {'field': field, 'canonical_field': canonical, **item}
        candidates = []
        for name in names:
            value = self.data.get(name, MISSING) if name in self.data else field_value(self.data, name)
            if value is not MISSING and value is not None: candidates.append((name, value))
        if not candidates and field=='business_line':
            product=self.get('product')[0]
            # Explicit controlled taxonomy classification, not fuzzy similarity.
            retail={'home loan','home equity line of credit','auto loan','secured personal loan','credit card'}
            if product is not None and normalized(product,'product') in retail:
                return 'Retail',None,{'field':field,'value':'Retail','binding':'policy-taxonomy-v1:retail-products','source_value':product}
        if not candidates: return None, None, {'field': field, 'status': 'MISSING'}
        facet={'product':'product','customer_segment':'customer_segment','geography':'geography'}.get(field)
        if len({normalized(v,facet) for _, v in candidates}) > 1:
            return None, None, {'field': field, 'status': 'CONFLICTING_ALIASES', 'candidates': candidates}
        name, value = candidates[0]
        unit = (self.data.get('fact_units') or {}).get(name) or KNOWN_UNITS.get(name)
        if name in ('loan_amount', 'requested_amount', 'exposure', 'collateral_value'):
            unit = unit or self.data.get('currency')
        return value, unit, {'field': field, 'binding': name, 'value': value, 'unit': unit,
                            'source': self.data.get('data_source') or 'Stored request facts',
                            'source_type':'SYNTHETIC' if name in self.data.get('synthetic_fields',[]) else 'STORED_REQUEST'}


def combined(values, logic='AND'):
    if not values: return None
    if logic == 'NOT': return None if len(values) != 1 or values[0] is None else not values[0]
    if logic == 'OR': return True if True in values else None if None in values else False
    return False if False in values else None if None in values else True


def comparison(actual, op, expected, facet=None):
    if actual is None: return None
    if op == 'EXISTS': return True
    if op in ('GT', 'GTE', 'LT', 'LTE'):
        if facet == 'ordered_rating' and isinstance(expected, str) and expected in RATINGS:
            actual = str(actual).strip().upper()
            if actual not in RATINGS:
                return None
            left, right = RATINGS.index(actual), RATINGS.index(expected)
        else:
            left, right = number(actual), number(expected)
        return {'GT': left > right, 'GTE': left >= right, 'LT': left < right, 'LTE': left <= right}[op]
    if op in ('EQ','NE') and isinstance(expected,(int,float,Decimal)) and not isinstance(expected,bool):
        match=number(actual)==number(expected)
        return match if op=='EQ' else not match
    values = expected if isinstance(expected, list) else [expected]
    actual_values = {normalized(a, facet) for a in (actual if isinstance(actual, list) else [actual])}
    expected_values = {normalized(v, facet) for v in values}
    match = bool(actual_values & expected_values)
    if facet == 'geography' and not match:
        relative = set(RELATIVE_JURISDICTIONS)
        if (expected_values & relative and not actual_values & relative) or (expected_values - relative and not actual_values - relative):
            return None
    if op in ('EQ', 'IN'): return match
    if op in ('NE', 'NOT_IN'): return not match
    return None


class GraphMatcher:
    def __init__(self, records, documents, clauses, scopes=()):
        self.records, self.documents = records, documents
        self.graph = assemble_graph(records)
        self.nodes = {n['id']: n for n in self.graph['nodes']}
        self.out, self.inc = defaultdict(list), defaultdict(list)
        for edge in self.graph['relationships']:
            self.out[edge['subject']].append(edge); self.inc[edge['object']].append(edge)
        self.rows = {r['id']: (record, r) for record in records for r in record['rules']}
        self.clauses = {c['id']: c for c in clauses}
        self.scopes = {s['policy_id']: s for s in scopes if s.get('kind') == 'policy_scope'}
        self.fingerprint = digest([VERSION, [(r['policy_id'], r['content_digest']) for r in records], documents, list(scopes)])

    def targets(self, node, predicate):
        return [e['object'] for e in self.out[node] if e['predicate'] == predicate]

    @staticmethod
    def scope_fact(facts, field, expected):
        values = expected if isinstance(expected, list) else [expected]
        if field == 'geography' and any(normalized(value) in RELATIVE_JURISDICTIONS for value in values):
            relative = facts.get('jurisdiction_relationship')
            if relative[0] is not None:
                if any(normalized(value) not in RELATIVE_JURISDICTIONS for value in values):
                    geography = facts.get(field)
                    if geography[0] is not None:
                        return [geography[0], relative[0]], None, {'geography': geography[2], 'jurisdiction_relationship': relative[2]}
                return relative
        return facts.get(field)

    def expression(self, node, facts, trace):
        value = self.nodes[node]; p = value['properties']
        if value['type'] == 'ConditionGroup':
            return combined([self.expression(child, facts, trace) for child in self.targets(node, 'HAS_MEMBER')], p['logic'])
        actual, unit, source = self.scope_fact(facts, p['field'], p.get('value'))
        try:
            comparable = converted(actual, unit, p.get('unit')) if actual is not None else None
            facet = 'ordered_rating' if p['field'] in ORDERED_RATING_FIELDS else {
                'product':'product','facility':'product','customer_segment':'customer_segment','geography':'geography'}.get(p['field'])
            outcome = comparison(comparable, p['operator'], p.get('value'), facet)
        except (ValueError, InvalidOperation, TypeError): outcome = None
        trace.append({'node_id': node, 'predicate': 'HAS_CONDITION', 'expected': p, 'fact': source, 'outcome': STATUS[outcome]})
        return outcome

    def policy_scope(self, doc, facts):
        vid='urn:cpi:version:'+str(doc.get('policy_version_id'))
        inclusions=self.targets(vid,'HAS_APPLICABILITY');exclusions=self.targets(vid,'HAS_EXCLUSION')
        if inclusions:
            trace=[]
            included=combined([self.expression(g,facts,trace) for g in inclusions])
            excluded=combined([self.expression(g,facts,trace) for g in exclusions],'OR') if exclusions else False
            outcome=combined([included,None if excluded is None else not excluded])
            trace.insert(0,{'predicate':'HAS_APPLICABILITY','node_ids':inclusions,'outcome':STATUS[outcome]})
            return outcome,trace
        record=next((r for r in self.records if r['policy_id']==doc['policy_id']),{})
        if (record.get('policy_scope') or {}).get('status') in ('PROPOSED','REJECTED'):
            return None,[{'predicate':'POLICY_SCOPE_NEEDS_REVIEW','outcome':STATUS[None]}]
        scope = self.scopes.get(doc['policy_id'])
        from .policy_scope import valid_scope
        version = {'id': doc.get('policy_version_id'), 'checksum': doc.get('checksum')}
        if not valid_scope(scope, version, list(self.clauses.values())): return None, []
        from .rule_engine import condition_result
        inclusion = True if scope.get('unrestricted') else condition_result(scope.get('conditions'), facts.data)[0]
        excluded = condition_result(scope['exclusions'], facts.data)[0] if scope.get('exclusions') else False
        return combined([inclusion, None if excluded is None else not excluded]), [
            {'predicate': 'REVIEWED_POLICY_SCOPE', 'clause_id': scope['clause_id'], 'source_quote': scope['source_excerpt']}]

    def match(self, proposal, evaluation_date=None):
        today = evaluation_date or date.today(); facts = Facts(proposal)
        cache = {}; decisions = []; policies = []; mappings = []
        documents = {d['policy_id']: d for d in self.documents}
        def rule_match(rid, doc, inherited, policy_trace, seen=()):
            if rid in cache: return cache[rid]
            if rid in seen: return None, []
            tests, trace = [], list(policy_trace)
            if inherited is not None or policy_trace: tests.append(inherited)
            for predicate, field, code, facet in [('APPLIES_TO_PRODUCT','product','product_code','product'),
                ('APPLIES_TO_SEGMENT','customer_segment','segment_code','customer_segment'),
                ('APPLIES_IN','geography','geography_code','geography')]:
                targets = self.targets(rid, predicate)
                if not targets: continue
                expected = [self.nodes[n]['properties'][code] for n in targets]
                actual, _, source = self.scope_fact(facts, field, expected)
                outcome = comparison(actual, 'IN', expected, facet)
                tests.append(outcome); trace.append({'predicate': predicate,'node_ids': targets,'expected': expected,'fact': source,'outcome': STATUS[outcome]})
            for group in self.targets(rid, 'HAS_CONDITION'): tests.append(self.expression(group, facts, trace))
            # An exception inherits its exact base rule's applicability, never its
            # compliance result. Approval requirements cannot waive a breach.
            for edge in self.inc[rid]:
                if edge['predicate'] != 'IMPLEMENTED_BY_RULE': continue
                for base in self.targets(edge['subject'], 'EXCEPTION_TO'):
                    base_record = self.rows[base][0]; base_doc = documents[base_record['policy_id']]
                    base_scope, base_trace = self.policy_scope(base_doc, facts)
                    outcome, _ = rule_match(base, base_doc, base_scope, base_trace, (*seen,rid))
                    tests.append(outcome);trace.append({'predicate':'EXCEPTION_TO','node_id':base,'outcome':STATUS[outcome]})
            if not tests:
                trace.append({'predicate':'SCOPE_NOT_ESTABLISHED','outcome':STATUS[None]})
            outcome = combined(tests)
            effective = doc.get('effective_date')
            if not effective: outcome = False if outcome is False else None
            elif date.fromisoformat(str(effective)[:10]) > today: outcome = False
            if not effective: trace.append({'predicate':'EFFECTIVE_DATE_MISSING','outcome':STATUS[None]})
            for period_id in self.targets(rid, 'HAS_EFFECTIVE_PERIOD'):
                period = self.nodes[period_id]['properties']
                if not period['start_date'] <= today.isoformat() <= period.get('end_date', '9999-12-31'):
                    outcome = False
                    trace.append({'predicate': 'HAS_EFFECTIVE_PERIOD', 'node_id': period_id, 'outcome': STATUS[False]})
            cache[rid] = outcome, trace
            return outcome, trace

        for doc in self.documents:
            pid = doc['policy_id']; vid = 'urn:cpi:version:'+str(doc.get('policy_version_id'))
            # Traverse version -> section -> rule; also honor direct version containment.
            rule_ids = set(self.targets(vid,'CONTAINS_RULE'))
            sections = list(self.targets(vid,'CONTAINS_SECTION')); seen=set()
            while sections:
                section=sections.pop()
                if section in seen:continue
                seen.add(section); rule_ids.update(self.targets(section,'CONTAINS_RULE'))
                sections.extend(self.targets(section,'CONTAINS_SECTION'))
            scope, scope_trace = self.policy_scope(doc, facts)
            outcomes = []
            for rid in sorted(rule_ids):
                record,row=self.rows[rid]; outcome,trace=rule_match(rid,doc,scope,scope_trace)
                outcomes.append(outcome)
                missing=[str(t.get('fact',{}).get('field') or t['predicate']) for t in trace if t.get('outcome')==STATUS[None]]
                parent = next((e['subject'] for e in self.inc[rid] if e['predicate']=='CONTAINS_RULE'),vid)
                decisions.append({'candidate_id':rid,'candidate_type':'Rule','policy_id':pid,'policy_name':doc['title'],
                    'rule_name':row['extracted']['name'],'applicability':STATUS[outcome],
                    'reason':'All explicit graph applicability constraints match' if outcome is True else 'An explicit graph applicability constraint does not match' if outcome is False else 'Applicability needs request facts or source-backed policy scope',
                    'missing_information':sorted(set(missing)) if outcome is None else [], 'trace':trace,
                    'graph_path':['urn:cpi:policy:'+str(pid),vid,parent,rid], 'graph_node_id':rid,
                    'source_clause_id':row['extracted']['clause_id']})
            outcome = False if scope is False else True if True in outcomes else None if not outcomes or None in outcomes else False
            policy = {'candidate_id':str(pid),'candidate_type':'Policy','policy_id':pid,'policy_name':doc['title'],
                'applicability':STATUS[outcome],'reason':'Policy inclusion determined from current source-backed graph rule paths',
                'graph_node_id':'urn:cpi:policy:'+str(pid),'applicable_rule_count':outcomes.count(True),'unresolved_rule_count':outcomes.count(None)}
            policies.append(policy)
            if outcome is True: mappings.append({'policy_id':pid,'policy_name':doc['title'],'rule_count':outcomes.count(True),'unresolved_rule_count':outcomes.count(None)})
        coverage=[{'policy_id':r['policy_id'],'proposed_rules':sum(x['status']=='PROPOSED' for x in r['rules']),
                   'scope_status':(r.get('policy_scope') or {}).get('status','MISSING'),
                   'unresolved_passages':sum(c['disposition']=='UNRESOLVED' for c in r['coverage']),
                   'failed_batches':len(r.get('failed_batches',[]))} for r in self.records]
        return {'version':VERSION,'matching_method':'Deterministic semantic graph traversal',
            'knowledge_fingerprint':self.fingerprint,'request_fingerprint':digest(proposal),'evaluated_at':today.isoformat(),
            'decisions':[*policies,*decisions],'policy_mappings':mappings,'coverage':coverage,
            'unresolved_policy_count':sum(p['applicability']==STATUS[None] for p in policies),
            'unresolved_rule_count':sum(d['applicability']==STATUS[None] for d in decisions),
            'applicable_rule_count':sum(d['applicability']==STATUS[True] for d in decisions),
            'excluded_rule_count':sum(d['applicability']==STATUS[False] for d in decisions),
            'graph_rule_count':len(decisions),'missing_extraction_policy_ids':[d['policy_id'] for d in self.documents if not any(r['policy_id']==d['policy_id'] for r in self.records)]}


def load_matcher():
    from ..database import shared_policy_connection
    from ..risk_knowledge.repositories import PostgreSQLRepository
    from ..risk_knowledge.semantic_pipeline import current_records
    from ..risk_knowledge.policy_taxonomy import source_rows
    repo=PostgreSQLRepository(shared_policy_connection,None)
    documents,clauses=source_rows(shared_policy_connection)
    # Recheck snapshots against this source read as well as current_records SQL.
    records=[r for r in current_records(repo) if any(d['policy_version_id']==r['policy_version_id'] and d['checksum']==r['source_checksum'] and d['version']==d['catalog_version'] for d in documents)]
    return GraphMatcher(records,documents,clauses,[m for m in repo.all('metadata') if m.get('kind')=='policy_scope'])
