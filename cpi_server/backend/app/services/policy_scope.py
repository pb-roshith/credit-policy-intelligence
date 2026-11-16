"""Graph retrieval and deterministic applicability. This module never calls an LLM."""
import hashlib
import json
from copy import deepcopy
from datetime import date
from ..database import shared_policy_connection
from ..risk_knowledge.catalog import read_catalog, project_catalog
from ..risk_knowledge.graph import NetworkXGraphRepository
from ..risk_knowledge.repositories import PostgreSQLRepository
from ..risk_knowledge.taxonomy import TaxonomyService
from ..agents.credit_request_policy_applicability import CreditRequestPolicyApplicabilityAgent
from .inventory_schema import Condition
from .rule_engine import condition_result, field_value, MISSING

APPLICABILITY_VERSION = 'graph-applicability-v1'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def condition_fields(condition):
    if not condition:
        return set()
    if condition.get('field'):
        return {condition['field']}
    return {f for group in ('all', 'any') for child in condition.get(group) or [] for f in condition_fields(child)}


def load_knowledge(rules):
    repo = PostgreSQLRepository(shared_policy_connection, None)
    policies, clauses, catalog_rules = read_catalog(shared_policy_connection)
    with shared_policy_connection() as db:
        versions = db.execute('SELECT id,policy_id,checksum,effective_date FROM policy_versions WHERE is_current').fetchall()
    concepts = repo.all('taxonomy_concepts')
    relationships = repo.all('ontology_relationships')
    metadata=repo.all('metadata')
    scopes = {s['policy_id']: s for s in metadata if s.get('kind') == 'policy_scope'}
    from ..risk_knowledge.policy_representation import current_representations
    representations={s['id']:s for s in current_representations(metadata,versions)}
    ids = {r['id'] for r in rules}
    catalog_by_id={r['id']:r for r in catalog_rules}
    # A pending draft must not hide an otherwise valid approved predecessor.
    # The caller supplies authoritative effective/approved SQL candidates; each
    # is still checked against the current source graph below.
    selected=[deepcopy(catalog_by_id.get(r['id'],r)) for r in rules]
    from ..risk_knowledge.representation_governance import check_definition
    from ..risk_knowledge.policy_representation import compile_graph,coverage_summary
    from ..risk_knowledge.rule_readiness import dependency_state
    dependency_reviews={r['rule_key']:r for r in metadata if r.get('kind')=='rule_dependency_review'}
    from fastapi import HTTPException
    compiled_cache={}
    for rule in selected:
        identifier=rule['definition'].get('representation_id')
        if identifier:
            rep=representations.get(identifier)
            version=next((v for v in versions if v['id']==rule['policy_version_id']),None)
            try:
                if not rep or not version or version['checksum']!=rep['source_checksum']:
                    raise HTTPException(409,'Stale policy representation')
                source_clauses=[c for c in clauses if c['policy_version_id']==rule['policy_version_id']]
                if identifier not in compiled_cache:compiled_cache[identifier]=compile_graph(rep,source_clauses)
                check_definition(rule,rep,source_clauses,compiled=compiled_cache[identifier])
                rule['graph_compilation_verified']=True
                review=dependency_reviews.get(rule['rule_key'])
                state=dependency_state(rule,rep,review)
                rule['_dependency_state']=state
                rule['_dependency_review']=review if state['review_current'] else None
                if not state['ready']:rule['review_required']=True
            except (HTTPException,ValueError):
                rule['review_required']=True
    graph = NetworkXGraphRepository()
    approved = {c['concept_id']: c for c in concepts if c['status'] == 'APPROVED'}
    nodes = [{'id': c['concept_id'], 'label': c['preferred_name'], 'type': c['kind'],
              'status': c['status'], 'risk_domain': c['risk_domain'],
              'source_name': c['source']['document_name'], 'provenance': c['source'], 'payload': c}
             for c in approved.values()]
    edges = [{'id': r['relationship_id'], 'source': r['subject'], 'target': r['object'],
              'predicate': r['predicate'], 'status': 'APPROVED', 'provenance': r['source']}
             for r in relationships if r['status'] == 'APPROVED'
             and r['subject'] in approved and r['object'] in approved]
    graph.replace(nodes, edges)
    project_catalog(graph, policies, clauses, selected, scopes=list(scopes.values()))
    from ..risk_knowledge.policy_representation import project_representations
    project_representations(graph,list(representations.values()),selected)
    return {'graph': graph, 'policies': policies, 'clauses': clauses, 'rules': selected,
            'versions': {v['policy_id']: v for v in versions}, 'scopes': scopes, 'concepts': concepts,
            'representations':representations,
            'fingerprint': fingerprint([policies, clauses, selected, versions, scopes, concepts, relationships,representations])}


def valid_scope(scope, version, clauses):
    if not scope or not version or scope.get('status') != 'APPROVED' or not scope.get('approved_by'):
        return False
    if scope.get('policy_version_id') != version['id'] or scope.get('source_checksum') != version['checksum']:
        return False
    source = next((c for c in clauses if c['id'] == scope.get('clause_id') and c['policy_version_id'] == version['id']), None)
    if not source or not scope.get('source_excerpt') or scope['source_excerpt'] not in source['source_excerpt']:
        return False
    if not scope.get('unrestricted') and not scope.get('conditions'):
        return False
    try:
        for key in ('conditions', 'exclusions'):
            if scope.get(key):
                Condition.model_validate(scope[key])
    except ValueError:
        return False
    return True


def policy_decisions(proposal, rules, evaluation_date, knowledge=None):
    knowledge = knowledge or load_knowledge(rules)
    results = []
    for policy in knowledge['policies']:
        pid = policy['policy_id']
        scope, version = knowledge['scopes'].get(pid), knowledge['versions'].get(pid)
        fields, missing, outcome = set(), [], None
        if not valid_scope(scope, version, knowledge['clauses']):
            missing = ['Approved policy scope for the current source version']
            reasons = ['Policy scope is absent, unapproved, or stale; scope is never inferred from titles or thresholds']
            # A reviewed rule context can be evaluated independently without
            # claiming that the entire policy has been interpreted.
            from ..risk_knowledge.rule_readiness import effective_rule
            from ..agents.credit_request_policy_applicability import evaluate_conditions
            contexts=[r for r in knowledge['rules'] if r['policy_id']==pid and r.get('graph_compilation_verified')
                      and r.get('_dependency_state',{}).get('ready') and r['status'] in ('Approved','Active')]
            context_results=[]
            for candidate in contexts:
                definition=effective_rule(candidate)['definition']
                result,absent,why=evaluate_conditions(definition,proposal)
                context_results.append(result)
                if result is not False:missing.extend(absent)
                fields|=condition_fields(definition.get('applicability_conditions'))|condition_fields(definition.get('applicability_exclusions'))
            if any(value is True for value in context_results):
                outcome=True;missing=[]
                reasons=['Request matches an explicitly reviewed rule context; this is not a completeness claim for the whole policy']
            elif contexts:
                missing=[m for m in missing if m!='Approved policy scope for the current source version']
                if not missing:missing=['Other policy scope is not yet established']
                reasons=['No reviewed rule context can currently confirm inclusion; other policy requirements may remain unresolved']
        else:
            fields = condition_fields(scope.get('conditions')) | condition_fields(scope.get('exclusions'))
            outcome, missing, reasons = condition_result(scope.get('conditions'), proposal)
            if scope.get('exclusions'):
                excluded, absent, why = condition_result(scope['exclusions'], proposal)
                reasons += ['Exclusion: ' + reason for reason in why]
                if excluded is True:
                    outcome = False
                elif excluded is None and outcome is not False:
                    outcome, missing = None, missing + absent
            reasons.append('Approved source clause ' + str(scope['clause_id']))
        if version and version.get('effective_date') and version['effective_date'] > evaluation_date:
            outcome, reasons = False, ['Policy is not yet effective']
        elif not version or not version.get('effective_date'):
            if outcome is not False:
                outcome = None
                missing.append('Policy effective date')
        results.append({'candidate_id': str(pid), 'candidate_type': 'Policy',
                        'applicability': 'Applicable' if outcome is True else 'Not Applicable' if outcome is False else 'Unable to Determine',
                        'reason': policy['title'] + ': ' + '; '.join(reasons),
                        'evaluated_attributes': {f: None if field_value(proposal, f) is MISSING else field_value(proposal, f) for f in sorted(fields)},
                        'missing_information': sorted(set(missing)) if outcome is None else [],
                        'graph_node_id': 'CPI-POLICY-' + str(pid)})
    return results


def policy_first_applicability(proposal, rules, current_stage, evaluation_date=None, *, knowledge=None):
    today = evaluation_date or date.today()
    knowledge = knowledge or load_knowledge(rules)
    data = {**proposal, 'status': current_stage}
    request_fingerprint = fingerprint(data)
    data = deepcopy(data)
    taxonomy = TaxonomyService(knowledge.get('concepts', []))
    normalization = []
    fields = {c.metadata.get('request_attribute') for c in taxonomy.concepts if c.status == 'APPROVED'} - {None, ''}
    for field in sorted(fields):
        if taxonomy.field(field) is None:
            continue
        actual = field_value(data, field)
        if actual is MISSING:
            continue
        normalized, evidence = taxonomy.normalize(field, actual)
        if evidence:
            target = data
            names = field.split('.')
            for name in names[:-1]:
                target = target[name]
            target[names[-1]] = normalized
            normalization.append(evidence)
    policies = policy_decisions(data, rules, today, knowledge)
    by_policy = {d['candidate_id']: d for d in policies}
    # Only policy -> exact clause <- approved rule paths establish candidates.
    # General ontology predicates never waive a scope condition or imply inclusion.
    paths, retrieved = knowledge['graph'].governed_rule_paths(), {}
    for rule in knowledge['rules']:
        rid, pid = 'CPI-RULE-' + str(rule['id']), 'CPI-POLICY-' + str(rule['policy_id'])
        if rid in paths and paths[rid][0] == pid:
            retrieved[str(rule['id'])] = paths[rid]
    from ..risk_knowledge.rule_readiness import effective_rule
    knowledge_by_id={r['id']:r for r in knowledge['rules']}
    eligible = [effective_rule({**r,'_dependency_review':knowledge_by_id[r['id']].get('_dependency_review')})
                for r in rules if str(r['id']) in retrieved
                and by_policy.get(str(r['policy_id']), {}).get('applicability') == 'Applicable']
    report = CreditRequestPolicyApplicabilityAgent().run(data, eligible, data.get('status'), today)
    checked = {d['candidate_id']: d for d in report['decisions'] if d['candidate_type'] == 'Rule'}
    decisions = list(policies)
    for rule in rules:
        rid, policy = str(rule['id']), by_policy.get(str(rule['policy_id']))
        decision = checked.get(rid)
        if decision is None:
            excluded = policy and policy['applicability'] == 'Not Applicable'
            decision = {'candidate_id': rid, 'candidate_type': 'Rule',
                        'applicability': 'Not Applicable' if excluded else 'Unable to Determine',
                        'reason': policy['reason'] if policy and policy['applicability'] != 'Applicable' else 'Approved current rule and exact policy/clause graph path required',
                        'evaluated_attributes': {},
                        'missing_information': [] if excluded else (policy['missing_information'] if policy and policy['missing_information'] else ['Approved source-backed rule path'])}
            dependency=knowledge_by_id.get(rule['id'],{}).get('_dependency_state')
            if dependency and not dependency['ready'] and not excluded:
                decision.update(applicability='Unable to Determine',reason='Relevant rule dependencies need review: '+'; '.join(dependency['blockers']),missing_information=dependency['blockers'])
        decisions.append({**decision, 'graph_node_id': 'CPI-RULE-' + rid, 'graph_path': retrieved.get(rid, [])})
    mappings = []
    for policy in policies:
        if policy['applicability'] != 'Applicable':
            continue
        pid = int(policy['candidate_id'])
        matched = [r for r in eligible if r['policy_id'] == pid and checked[str(r['id'])]['applicability'] == 'Applicable']
        source = next(p for p in knowledge['policies'] if p['policy_id'] == pid)
        mappings.append({'policy_id': pid, 'policy_name': source['title'], 'reason': policy['reason'],
                         'rule_count': len(matched), 'rule_version_ids': [r['id'] for r in matched]})
    from ..risk_knowledge.policy_representation import coverage_summary
    applicable_policy_ids={int(p['candidate_id']) for p in policies if p['applicability']=='Applicable'}
    policy_coverage=[{'policy_id':rep['policy_id'],**coverage_summary(rep)} for rep in knowledge.get('representations',{}).values() if rep['policy_id'] in applicable_policy_ids]
    return {**report, 'decisions': decisions, 'policy_mappings': mappings,
            'policy_coverage':policy_coverage,'incomplete_policy_ids':[c['policy_id'] for c in policy_coverage if not c['complete']],
            'dependency_reviews':{str(r['id']):r['_dependency_review'] for r in knowledge['rules'] if r.get('_dependency_review') and r.get('_dependency_state',{}).get('ready')},
            'applicability_version': APPLICABILITY_VERSION, 'knowledge_fingerprint': knowledge['fingerprint'],
            'request_fingerprint': request_fingerprint, 'taxonomy_normalization': normalization,
            'retrieval': {'method': 'NetworkX policy CONTAINS clause <- DERIVED_FROM approved rule; explicit scope and rule conditions',
                          'llm_used': False, 'source_backed_rule_count': len(retrieved)},
            'unresolved_policy_count': sum(d['applicability'] == 'Unable to Determine' for d in policies)}
