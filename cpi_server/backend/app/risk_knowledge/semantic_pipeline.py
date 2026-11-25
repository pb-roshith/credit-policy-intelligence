"""Durable sequential enrichment: sources -> AI -> validation -> approved graph."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import re
from pydantic import ValidationError
from .repositories import PostgreSQLRepository
from .semantic_extraction import (PIPELINE_VERSION, ACTOR, ExtractionBatch, ExtractedRule,
    llm_extract, digest, rule_id, validate_rule, taxonomy_context, sources_in_batches,
    relevant_rules, assemble_graph, restore_source_wrapping, retrieval_neighborhood,normative_clause)
from .semantic_model import semantic_contract, validate_instance, VERSION, COMPATIBLE_VERSIONS
from .policy_taxonomy import structural_reason,heading_for


def current_records(repo):
    if isinstance(repo, PostgreSQLRepository):
        with repo.connection_factory() as c:
            rows = c.execute("""SELECT k.payload FROM risk_knowledge_objects k
                JOIN policy_versions v ON v.id=(k.payload->>'policy_version_id')::bigint
                JOIN policy_documents p ON p.policy_id=v.policy_id
                WHERE k.kind='metadata' AND k.owner_id='' AND k.payload->>'kind'='semantic_policy'
                AND v.is_current AND v.checksum=k.payload->>'source_checksum' AND v.version=p.version
                ORDER BY p.policy_id""").fetchall()
        return [r['payload'] for r in rows]
    return [r for r in repo.all('metadata') if r.get('kind') == 'semantic_policy']


def seal(record):
    record['content_digest'] = digest({k: v for k, v in record.items() if k != 'content_digest'})
    return record


def save(repo, record, expected, actor, action):
    seal(record)
    if isinstance(repo, PostgreSQLRepository):
        # Lock the source version through publication so stale work cannot be
        # published after a concurrent policy change.
        from psycopg.types.json import Jsonb
        with repo.connection_factory() as c:
            source = c.execute('SELECT v.checksum,v.is_current,v.version,p.version AS catalog_version FROM policy_versions v JOIN policy_documents p USING(policy_id) WHERE v.id=%s FOR SHARE OF v,p', (record['policy_version_id'],)).fetchone()
            if not source or not source['is_current'] or source['checksum'] != record['source_checksum'] or source['version'] != source['catalog_version']:
                raise ValueError('Source changed before semantic publication; retry current policy')
            if expected is None:
                result = c.execute("INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES ('metadata','',%s,%s) ON CONFLICT DO NOTHING", (record['id'], Jsonb(record)))
            else:
                old = c.execute("""SELECT payload FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id=''
                    AND id=%s AND payload->>'content_digest'=%s FOR UPDATE""", (record['id'], expected)).fetchone()
                if old and old['payload']['policy_version_id'] != record['policy_version_id']:
                    previous = old['payload']
                    archive_id = record['id'] + '-VERSION-' + str(previous['policy_version_id'])
                    c.execute("""INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES ('metadata','',%s,%s)
                        ON CONFLICT(kind,owner_id,id) DO NOTHING""",
                        (archive_id, Jsonb({**previous, 'id': archive_id, 'kind': 'semantic_policy_history'})))
                result = c.execute("UPDATE risk_knowledge_objects SET payload=%s WHERE kind='metadata' AND owner_id='' AND id=%s AND payload->>'content_digest'=%s", (Jsonb(record), record['id'], expected))
            if result.rowcount != 1: raise ValueError('Knowledge was edited concurrently; reload before retrying')
            c.execute("INSERT INTO audit_events(entity_type,entity_id,new_value,action,actor,reason) VALUES ('SemanticPolicy',%s,%s,%s,%s,%s)", (record['id'], Jsonb({'content_digest': record['content_digest'], 'rules': len(record['rules'])}), action, actor, 'Source-validated AI extraction; automatic initial approval is overridable'))
    elif not repo.compare_and_put('metadata', record['id'], record, expected, {'actor': actor, 'action': action}):
        raise ValueError('Knowledge was edited concurrently; reload before retrying')


def resolve_record_references(record, known):
    available = {r['id'] for k in [*known,record] for r in k['rules'] if r['status']=='APPROVED'}
    for row in record['rules']:
        ref = row['extracted'].get('base_rule_ref')
        if not ref or row['status']!='APPROVED': continue
        if ref.startswith('clause:'):
            m = re.fullmatch(r'clause:(\d+):rule:(\d+)',ref)
            ref = rule_id(record['policy_version_id'],int(m[1]),int(m[2])) if m else None
        error = None
        if ref not in available or ref==row['id']:
            error='Exception target is not an approved current rule'
        elif not row.get('human_override') and re.search(r'\babove\b|aforementioned|previous',row['extracted'].get('reference_quote') or '',re.I):
            target=next(((k,r) for k in [*known,record] for r in k['rules'] if r['id']==ref),None)
            if not target or target[0]['policy_id']!=record['policy_id']:
                error='Relative exception reference cannot identify a rule in another policy without an explicit cross-reference'
            else:
                metric_keys={m['key'] for m in target[1]['extracted']['metrics']}
                choices=[r for r in record['rules'] if r['status']=='APPROVED' and r['id']!=row['id']
                    and r['extracted']['clause_id']<row['extracted']['clause_id']
                    and metric_keys & {m['key'] for m in r['extracted']['metrics']}]
                if choices:
                    last=max(r['extracted']['clause_id'] for r in choices)
                    choices=[r for r in choices if r['extracted']['clause_id']==last]
                if len(choices)!=1 or choices[0]['id']!=ref:error='Relative exception antecedent is ambiguous; choose an exact source-backed target'
        if error:row.update(status='PROPOSED',validation_error=error,approved_by=None,approval_mode=None)


def process_source(policy, version, clauses, repo, *, provider=llm_extract, progress=None, batcher=None):
    identifier = 'SEMANTIC-POLICY-' + str(policy['policy_id'])
    previous = repo.get('metadata', identifier)
    expected = previous['content_digest'] if previous else None
    source_digest = digest([(c['id'], c['source_excerpt']) for c in clauses])
    reusable = previous and previous['policy_version_id'] == version['id'] and previous['source_digest'] == source_digest and previous.get('pipeline') == PIPELINE_VERSION and previous.get('ontology_version') in COMPATIBLE_VERSIONS
    record = deepcopy(previous) if reusable else {
        'id': identifier, 'kind': 'semantic_policy', 'pipeline': PIPELINE_VERSION,
        'ontology_version': VERSION, 'policy_id': policy['policy_id'], 'policy_name': policy['title'],
        'policy_version_id': version['id'], 'policy_version': version['version'],
        'source_checksum': version['checksum'], 'source_digest': source_digest,
        'synthetic': str(policy.get('source_type', '')).lower() in ('manufactured', 'synthetic') or any(re.search(r'synthetic (?:training|policy|demonstration)|fictional', c['source_excerpt'], re.I) for c in clauses),
        'source_clauses': [{k: c.get(k) for k in ('id', 'sequence', 'source_excerpt', 'section_heading', 'clause_number', 'page_number')} for c in clauses],
        'rules': [], 'coverage': [], 'completed_batches': [], 'failed_batches': [], 'context_history': [],
    }
    if version.get('effective_date'):
        record['effective_date'] = str(version['effective_date'])
    known = [r for r in current_records(repo) if r['policy_id'] != policy['policy_id']]
    taxonomy = taxonomy_context()
    taxonomy_ids = {c['id'] for c in taxonomy}
    # Entire scope/definitions passages may inform extraction only with explicit
    # quoted supporting-source links; no automatic inheritance of scope.
    context_clauses, size = [], 0
    for c in clauses:
        if re.search(r'\bscope\b|applicability|definitions', (c.get('section_heading') or '') + '\n' + c['source_excerpt'].split('\n')[0], re.I):
            if size + len(c['source_excerpt']) <= 9000:
                context_clauses.append(c); size += len(c['source_excerpt'])
    structural={c['id']:structural_reason(c['source_excerpt'],heading_for(c)) for c in clauses}
    structural={cid:reason for cid,reason in structural.items() if reason}
    record['rules']=[r for r in record['rules'] if r['extracted']['clause_id'] not in structural or r.get('human_override')]
    record['coverage']=[c for c in record['coverage'] if c['clause_id'] not in structural]
    record['coverage'] += [{'clause_id':cid,'disposition':'NON_RULE','ai_disposition':'NON_RULE','reason':reason} for cid,reason in structural.items()]
    primary_clauses=[c for c in clauses if c['id'] not in structural]
    batches = list((batcher or sources_in_batches)(primary_clauses))
    failed = []
    for index, batch in enumerate(batches):
        batch_sources = [(c['id'], c['source_excerpt']) for c in batch]
        batch_key = digest([VERSION, PIPELINE_VERSION, batch_sources])
        compatible_keys = {digest([known_version, PIPELINE_VERSION, batch_sources]) for known_version in COMPATIBLE_VERSIONS}
        batch_ids={c['id'] for c in batch}
        if compatible_keys.intersection(record['completed_batches']) and not any(c['disposition']=='UNRESOLVED' for c in record['coverage'] if c['clause_id'] in batch_ids) and not any(r['status']=='PROPOSED' for r in record['rules'] if r['extracted']['clause_id'] in batch_ids): continue
        record['completed_batches']=[k for k in record['completed_batches'] if k not in compatible_keys]
        if progress: progress(index, stage='extraction', details={'pipeline': PIPELINE_VERSION, 'policy_name': policy['title'], 'total_batches': len(batches)})
        candidates = relevant_rules([*known, record], '\n'.join(c['source_excerpt'] for c in batch))
        neighborhood=retrieval_neighborhood([*known,record],[c['id'] for c in candidates])
        antecedents=[];antecedent_size=0;antecedent_ids=set()
        for candidate in candidates:
            cid=candidate['rule']['clause_id'];quote=candidate['rule']['source_quote']
            if candidate['policy_version_id']==version['id'] and cid not in antecedent_ids and antecedent_size+len(quote)<=8000:
                antecedents.append({'id':cid,'source_excerpt':quote});antecedent_ids.add(cid);antecedent_size+=len(quote)
        context = {'ontology': semantic_contract(), 'taxonomy': taxonomy,
            'primary_clauses': batch, 'source_context': context_clauses,
            'existing_graph_rules': candidates, 'existing_graph_neighborhood':neighborhood,
            'antecedent_sources':antecedents,
            'policy': {'id': policy['policy_id'], 'title': policy['title'], 'version': version['version']}}
        primary = {c['id']: c for c in batch}
        supplied = {c['id']: c for c in [*antecedents,*context_clauses, *batch]}
        try:
            result = None
            for attempt in range(2):
                try:
                    result = ExtractionBatch.model_validate(provider(context))
                    if len(result.coverage) != len(primary) or {r.clause_id for r in result.coverage} != set(primary):
                        raise ValueError('AI omitted or duplicated a primary clause disposition')
                    if len({(r.clause_id, r.rule_sequence) for r in result.rules}) != len(result.rules):
                        raise ValueError('AI duplicated atomic rule identities')
                    if any(r.clause_id not in primary for r in result.rules): raise ValueError('AI extracted a rule from outside the primary batch')
                    result.rules = [r for r in result.rules if not re.search(r'(?i)\bnon[- ]rule\b|^no rule',r.name)]
                    if not result.rules:
                        normative=[c['id'] for c in batch if re.search(r'\bshall\b|\bmust\b|is required|required to',c['source_excerpt'],re.I)
                            and not re.search(r'training|scenario|suggested.*prompt',c.get('section_heading') or '',re.I)]
                        if normative:
                            for disposition in result.coverage:
                                if disposition.clause_id in normative:
                                    disposition.disposition='UNRESOLVED'
                                    disposition.reason='Normative source language was returned without an extracted requirement'
                            if not attempt:
                                context['retry_instruction']='Normative primary clauses '+str(normative)+' contain requirements. Extract them even if the policy is labelled synthetic.'
                                continue
                    for r in result.rules: restore_source_wrapping(r, primary, supplied)
                    issues = [{'clause_id': r.clause_id, 'rule_sequence': r.rule_sequence,
                        'reason': validate_rule(r,primary,supplied,{c['id'] for c in candidates},taxonomy_ids)} for r in result.rules]
                    issues = [i for i in issues if i['reason']]
                    rule_sources={r.clause_id for r in result.rules}|{s.clause_id for r in result.rules for s in r.supporting_sources}
                    for disposition in result.coverage:
                        if disposition.disposition=='NON_RULE' and disposition.clause_id not in rule_sources and normative_clause(primary[disposition.clause_id]):
                            disposition.disposition='UNRESOLVED'
                            disposition.reason='Normative source passage has no extracted requirement or supporting-source link'
                            issues.append({'clause_id':disposition.clause_id,'reason':disposition.reason})
                    if issues and not attempt:
                        context['validation_feedback'] = issues
                        context['retry_instruction'] = 'Correct these source/atomicity errors. Split limits by product, programme or segment, retain all conditions, and return the complete batch again.'
                        continue
                    break
                except Exception as error:
                    if attempt: raise
                    errors=[{'path':list(e['loc']),'type':e['type']} for e in error.errors(include_input=False,include_context=False)[:10]] if isinstance(error,ValidationError) else str(error)[:500]
                    context['retry_instruction'] = 'Previous response failed validation: ' + json.dumps(errors) + '. Return complete, exact-source structured output. Put rule objects only in rules; coverage objects contain only clause_id, disposition and reason.'
            new_rules = []
            protected={r['id'] for r in record['rules'] if r.get('human_override') or r['status']=='APPROVED'}
            for rule in result.rules:
                reason = validate_rule(rule, primary, supplied, {c['id'] for c in candidates}, taxonomy_ids)
                rid = rule_id(version['id'], rule.clause_id, rule.rule_sequence)
                existing = next((r for r in record['rules'] if r['id'] == rid), None)
                if existing and existing.get('human_override'):
                    new_rules.append(existing); continue
                if existing and existing['status']=='APPROVED' and reason:
                    retained=deepcopy(existing)
                    retained['latest_proposal']={'extracted':rule.model_dump(mode='json'),'validation_error':reason}
                    new_rules.append(retained);continue
                new_rules.append({'id': rid, 'extracted': rule.model_dump(mode='json'),
                    'status': 'PROPOSED' if reason else 'APPROVED', 'validation_error': reason,
                    'approved_by': None if reason else ACTOR, 'approval_mode': 'AUTOMATIC' if not reason else None,
                    'human_override': False, 'review_history': []})
            preserved = [r for r in record['rules'] if (r.get('human_override') or r['status']=='APPROVED') and r['extracted']['clause_id'] in primary]
            new_rules += [r for r in preserved if r['id'] not in {n['id'] for n in new_rules}]
            batch_clauses = set(primary)
            record['rules'] = [r for r in record['rules'] if r['extracted']['clause_id'] not in batch_clauses] + new_rules
            record['coverage'] = [r for r in record['coverage'] if r['clause_id'] not in batch_clauses]
            for disposition in result.coverage:
                rows = [r for r in new_rules if r['extracted']['clause_id'] == disposition.clause_id]
                item = disposition.model_dump()
                item['ai_disposition'] = disposition.disposition
                if any(r['status'] == 'PROPOSED' for r in rows) or (disposition.disposition == 'RULES' and not rows):
                    item['disposition'] = 'UNRESOLVED'; item['reason'] = '; '.join(r['validation_error'] or '' for r in rows) or 'Rule disposition has no extracted requirements'
                if rows and disposition.disposition == 'NON_RULE':
                    item['disposition'] = 'UNRESOLVED'; item['reason'] = 'AI returned rules for a non-rule passage'
                    for r in rows:
                        if r['id'] not in protected:r.update(status='PROPOSED', validation_error=item['reason'], approved_by=None)
                record['coverage'].append(item)
            # Do not publish dangling exception references.
            resolve_record_references(record,known)
            for coverage in record['coverage']:
                pending=[r for r in record['rules'] if r['extracted']['clause_id']==coverage['clause_id'] and r['status']=='PROPOSED']
                if pending:coverage.update(disposition='UNRESOLVED',reason='; '.join(sorted({r['validation_error'] or 'Unresolved extraction' for r in pending})))
            graph = assemble_graph([*known, record])
            validation = validate_instance(graph)
            if not validation['conforms']:
                raise ValueError('Semantic publication rejected: ' + json.dumps(validation['errors'][:3]))
            if not any(c['disposition'] == 'UNRESOLVED' for c in record['coverage'] if c['clause_id'] in primary) and not any(r['status'] == 'PROPOSED' for r in new_rules):
                record['completed_batches'].append(batch_key)
            record['context_history'].append({'batch': batch_key, 'graph_rule_ids': [c['id'] for c in candidates],
                'graph_context_digest': digest({'rules':candidates,'neighborhood':neighborhood}),
                'graph_neighborhood_nodes':len(neighborhood['entities']),
                'ontology_version': VERSION, 'taxonomy_digest': digest(taxonomy)})
            record['updated_at'] = datetime.now(timezone.utc).isoformat()
            save(repo, record, expected, ACTOR, 'EXTRACT_VALIDATE_PUBLISH')
            expected = record['content_digest']
        except Exception as error:
            # Reload the last committed state: failed graph validation cannot
            # leak its uncommitted rules into a later batch or retrieval context.
            committed = repo.get('metadata', identifier)
            if committed and committed.get('source_digest') == source_digest:
                record = deepcopy(committed); expected = record['content_digest']
            else:
                record['rules'] = []; record['coverage'] = []; record['completed_batches'] = []; record['context_history'] = []
            failed.append({'batch': batch_key, 'clause_ids': sorted(primary),
                'error': str(error)[:1200] if isinstance(error, ValueError) else type(error).__name__})
    record['failed_batches'] = failed
    record['updated_at'] = datetime.now(timezone.utc).isoformat()
    save(repo, record, expected, ACTOR, 'SEMANTIC_EXTRACTION_RESULT')
    if provider is llm_extract:
        from .semantic_scope import enrich_scope
        try:
            record=enrich_scope(repo,record)
        except Exception as error:
            # Rules stay available; missing scope is explicitly unresolved by
            # graph matching and can be retried independently of rule extraction.
            logging.getLogger(__name__).warning("Policy scope enrichment failed (%s)", type(error).__name__)
    approved = sum(r['status'] == 'APPROVED' for r in record['rules'])
    unresolved = len(clauses) - len(record['coverage']) + sum(r['disposition'] == 'UNRESOLVED' for r in record['coverage'])
    unresolved += sum(r['status'] == 'PROPOSED' for r in record['rules'])
    return {'policy_id': policy['policy_id'], 'policy_name': policy['title'], 'pipeline': PIPELINE_VERSION,
        'status': 'Completed with errors' if failed or unresolved else 'Completed', 'partial_result': bool(failed or unresolved),
        'clauses_processed': len(record['coverage']), 'clauses_discovered': len(clauses), 'rules_proposed': len(record['rules']),
        'rules_approved': approved, 'quantitative_rules': sum(r['extracted']['rule_kind'] == 'QUANTITATIVE' for r in record['rules']),
        'qualitative_rules': sum(r['extracted']['rule_kind'] != 'QUANTITATIVE' for r in record['rules']),
        'manual_review_rules': len(record['rules']) - approved, 'unresolved_spans': unresolved,
        'validation_failures': len(failed), 'failed_batches': len(failed), 'failures': failed,
        'semantic_record_id': record['id'], 'graph_context_batches': len(record['context_history'])}


def process_policy(policy_id, user, job_id=None, progress=None):
    from ..database import shared_policy_connection
    from ..services.policy_ingestion import ingest_policy
    policy, version, _, clauses = ingest_policy(policy_id)
    if not clauses: raise ValueError('No extractable current policy source')
    repo = PostgreSQLRepository(shared_policy_connection, user['user_id'])
    previous=repo.get('metadata','SEMANTIC-POLICY-'+str(policy_id))
    # A large-document response with no requirements gets narrower recovery
    # batches, rather than repeatedly asking the same broad question.
    narrow=previous and not previous.get('rules') and any(normative_clause(c) for c in clauses)
    batcher=(lambda rows:sources_in_batches(rows,max_clauses=1)) if narrow else None
    return process_source(policy, version, clauses, repo, progress=progress,batcher=batcher)


def review_rule(repo, rule_identifier, *, status, notes, actor, expected_digest, replacement=None):
    record = next((r for r in current_records(repo) if any(rule['id'] == rule_identifier for rule in r['rules'])), None)
    if not record: raise ValueError('Current semantic rule not found')
    if record['content_digest'] != expected_digest: raise ValueError('Knowledge changed; reload before overriding')
    if status not in ('APPROVED', 'REJECTED', 'PROPOSED'): raise ValueError('Unsupported review status')
    if len(notes.strip()) < 3: raise ValueError('Review rationale is required')
    row = next(r for r in record['rules'] if r['id'] == rule_identifier)
    before = deepcopy(row)
    if replacement is not None:
        rule = ExtractedRule.model_validate(replacement)
        if rule.clause_id != row['extracted']['clause_id'] or rule.rule_sequence != row['extracted']['rule_sequence']:
            raise ValueError('An override cannot change rule source identity')
        sources = {c['id']: c for c in record['source_clauses']}
        candidates = {r['id'] for k in current_records(repo) for r in k['rules'] if r['status'] == 'APPROVED'}
        error = validate_rule(rule, sources, sources, candidates, {t['id'] for t in taxonomy_context()})
        if error: raise ValueError(error)
        row['extracted'] = rule.model_dump(mode='json')
    elif status == 'APPROVED' and row.get('validation_error'):
        raise ValueError('Correct the validation error before approving this extraction')
    row.update(status=status, human_override=True, approved_by=actor if status == 'APPROVED' else None,
        approval_mode='HUMAN_OVERRIDE', validation_error=None if replacement else row.get('validation_error'))
    row['review_history'].append({'actor': actor, 'notes': notes, 'at': datetime.now(timezone.utc).isoformat(),
        'previous': {k: v for k, v in before.items() if k != 'review_history'}})
    others = [r for r in current_records(repo) if r['id'] != record['id']]
    validation = validate_instance(assemble_graph([*others, record]))
    if not validation['conforms']: raise ValueError('Override violates semantic constraints: ' + json.dumps(validation['errors'][:3]))
    save(repo, record, expected_digest, actor, 'HUMAN_SEMANTIC_OVERRIDE')
    return record
