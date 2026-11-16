"""Small, paginated graph neighborhoods; full source knowledge stays on server."""
from .semantic_extraction import assemble_graph, approved_rules


def graph_view(records, *, focus='', policy_id=None, offset=0, limit=6):
    instance = assemble_graph(records)
    nodes = {n['id']: n for n in instance['nodes']}
    edges = list(instance['relationships'])
    # A navigation shortcut over the authoritative version/section path. This
    # projection does not add assertions to the stored ontology instance.
    versions = {e['subject']: e['object'] for e in edges if e['predicate'] == 'VERSION_OF'}
    for edge in instance['relationships']:
        if edge['predicate'] == 'PART_OF_VERSION' and nodes[edge['subject']]['type'] == 'PolicyRule':
            policy = versions.get(edge['object'])
            if policy:
                edges.append({'id': 'navigation:' + policy + ':' + edge['subject'],
                    'subject': policy, 'object': edge['subject'], 'predicate': 'CONTAINS_RULE',
                    'status': edge['status'], 'source_refs': edge['source_refs'],
                    'derived': True, 'via': [edge['object']]})
    selected = []
    focus = focus or ('urn:cpi:policy:' + str(policy_id) if policy_id is not None else '')
    if focus and focus not in nodes: raise ValueError('Current graph node not found')
    limit = max(1, min(limit, 12)); offset = max(0, offset)
    if focus:
        adjacent = {e['object'] if e['subject'] == focus else e['subject'] for e in edges if focus in (e['subject'], e['object'])}
        # Provenance and classification remain accessible through inspection and
        # explicit expansion, after the business relationships.
        order = {'Product': 0, 'CustomerSegment': 1, 'RiskMetric': 2, 'Threshold': 3,
                 'Exception': 4, 'ApprovalRequirement': 5, 'ApprovalAuthority': 5,
                 'ConditionGroup': 6, 'Condition': 6, 'PolicyRule': 7, 'CreditPolicy': 8,
                 'PolicyVersion': 15, 'PolicySection': 16, 'SourcePassage': 20, 'TaxonomyConcept': 19}
        choices = sorted(adjacent, key=lambda i: (order.get(nodes[i]['type'], 6), nodes[i]['label'], i))
        selected = [focus, *choices[offset:offset+limit]]
    else:
        choices = sorted([n['id'] for n in nodes.values() if n['type'] == 'CreditPolicy'], key=lambda i: nodes[i]['label'])
        selected = choices[offset:offset+limit]
    selected = set(selected)
    def provenance(refs):
        source = nodes.get(refs[0]) if refs else None
        if not source: return None
        p = source['properties']
        record = next((r for r in records if str(r['policy_id']) == p['document_reference']), {})
        return {'document_id': 'CPI-POLICY-' + p['document_reference'], 'document_name': record.get('policy_name'),
            'passage': p['text'], 'page': p.get('page'), 'clause': p.get('clause_reference'),
            'version': p['version'], 'checksum': p['source_checksum'], 'origin': 'SEMANTIC_AI_EXTRACTION'}
    projected = [{**nodes[i], 'risk_domain': 'Credit Risk', 'provenance': provenance(nodes[i]['source_refs']),
        'payload': nodes[i]['properties'], 'source_name': (provenance(nodes[i]['source_refs']) or {}).get('document_name', ''),
        'neighbor_count': len({e['object'] if e['subject'] == i else e['subject'] for e in edges if i in (e['subject'], e['object'])})} for i in selected]
    projected_edges = [{'id': e['id'], 'source': e['subject'], 'target': e['object'], 'predicate': e['predicate'],
        'status': e['status'], 'derived': e.get('derived', False), 'via': e.get('via', []),
        'provenance': provenance(e['source_refs'])} for e in edges if e['subject'] in selected and e['object'] in selected]
    neighbors = [{'id': i, 'label': nodes[i]['label'], 'type': nodes[i]['type'], 'payload': nodes[i]['properties'],
        'relationships': sorted({e['predicate'] for e in edges if {e['subject'], e['object']} == {focus, i}})} for i in choices]
    return {'nodes': projected, 'edges': projected_edges, 'focus': focus,
        'neighbors': neighbors, 'offset': offset, 'limit': limit,
        'total_nodes': len(nodes), 'total_relationships': len(instance['relationships']), 'available_neighbors': len(choices),
        'next_offset': offset + limit if offset + limit < len(choices) else None, 'truncated': offset + limit < len(choices)}


def rule_inventory(records):
    active = approved_rules(records)
    return {'policies': [{'policy_id': r['policy_id'], 'title': r['policy_name'],
        'scope_status': (r.get('policy_scope') or {}).get('status','MISSING'),
        'rules': len(r['rules']), 'approved': sum(s['id'] in active for s in r['rules']),
        'unresolved_clauses': sum(c['disposition'] == 'UNRESOLVED' for c in r['coverage']),
        'failed_batches': len(r['failed_batches']), 'policy_version_id': r['policy_version_id']} for r in records],
        'unresolved':[{'policy_id':record['policy_id'],'policy_name':record['policy_name'],**coverage,
            'source':next(c for c in record['source_clauses'] if c['id']==coverage['clause_id'])}
            for record in records for coverage in record['coverage'] if coverage['disposition']=='UNRESOLVED'],
        'rules': [{**rule, 'policy_id': record['policy_id'], 'policy_name': record['policy_name'],
            'rule_category':'QUANTITATIVE' if rule['extracted']['rule_kind']=='QUANTITATIVE' or rule['extracted']['thresholds'] else 'QUALITATIVE',
            'policy_version': record['policy_version'], 'record_digest': record['content_digest'],
            'synthetic': record['synthetic'], 'published_in_graph': rule['id'] in active,
            'blocked_reason': 'Base rule is missing, rejected, stale or cyclic' if rule['status']=='APPROVED' and rule['id'] not in active else None,
            'source': next(c for c in record['source_clauses'] if c['id'] == rule['extracted']['clause_id'])}
            for record in records for rule in record['rules']]}


def policy_source_view(document, clauses, record=None, published_ids=()):
    """Join current source passages to current AI rules without a legacy build.

    Passage text is read from policy_clauses, not from generated rule summaries.
    Supporting citations remain distinguishable from the primary source clause.
    """
    current = (document.get('policy_version_id') is not None and
        str(document.get('version')) == str(document.get('catalog_version', document.get('version'))))
    matches = bool(current and record and
        record['policy_version_id'] == document['policy_version_id'] and
        record['source_checksum'] == document.get('checksum'))
    if not matches:
        record = None
    sources = {c['id']: c for c in clauses
        if c['policy_id'] == document['policy_id'] and c['policy_version_id'] == document.get('policy_version_id')}
    coverage = {c['clause_id']: c for c in record.get('coverage', [])} if record else {}
    primary, supporting = {}, {}
    rules = []
    for rule in record.get('rules', []) if record else []:
        extracted = rule['extracted']
        cid = extracted['clause_id']
        primary.setdefault(cid, []).append(rule['id'])
        support_verified = True
        for citation in extracted.get('supporting_sources', []):
            supporting.setdefault(citation['clause_id'], []).append(rule['id'])
            support_verified &= (citation['clause_id'] in sources and
                citation['quote'] in sources[citation['clause_id']]['source_excerpt'])
        rules.append({**rule, 'published_in_graph': rule['id'] in published_ids,
            'source_quote_verified': cid in sources and extracted['source_quote'] in sources[cid]['source_excerpt'],
            'supporting_quotes_verified': bool(support_verified)})
    passages = []
    for cid, clause in sorted(sources.items(), key=lambda item: (item[1].get('sequence', 0), item[0])):
        disposition = coverage.get(cid)
        passages.append({'clause_id': cid, 'sequence': clause.get('sequence'),
            'disposition': disposition['disposition'] if disposition else 'NOT_PROCESSED',
            'reason': disposition.get('reason') if disposition else 'This passage has not been processed by the current AI extraction.',
            'primary_rule_ids': list(dict.fromkeys(primary.get(cid, []))),
            'supporting_rule_ids': list(dict.fromkeys(supporting.get(cid, []))),
            'source': {'document_id': 'CPI-POLICY-' + str(document['policy_id']),
                'document_name': document['title'], 'version': str(document.get('version') or 'UNKNOWN'),
                'checksum': document.get('checksum'), 'effective_date': document.get('effective_date'),
                'passage': clause['source_excerpt'],
                'page': clause.get('page_number'), 'section': clause.get('section_heading'),
                'clause': clause.get('clause_number'), 'origin': 'CURRENT_POLICY_SOURCE'}})
    unprocessed = sum(p['disposition'] == 'NOT_PROCESSED' for p in passages)
    unresolved = sum(p['disposition'] == 'UNRESOLVED' for p in passages)
    proposed = sum(r['status'] == 'PROPOSED' for r in rules)
    return {'policy_id': document['policy_id'], 'policy_name': document['title'],
        'policy_version_id': document.get('policy_version_id'), 'policy_version': document.get('version'),
        'catalog_version': document.get('catalog_version'), 'source_checksum': document.get('checksum'),
        'source_status': 'CURRENT' if current else 'MISSING_OR_OUTDATED_SOURCE',
        'has_extraction': record is not None, 'pipeline': record.get('pipeline') if record else None,
        'ontology_version': record.get('ontology_version') if record else None,
        'record_digest': record.get('content_digest') if record else None,
        'policy_scope': record.get('policy_scope') if record else None,
        'passages': passages, 'rules': rules,
        'summary': {'source_passages': len(passages), 'extracted_rules': len(rules),
            'published_rules': sum(r['published_in_graph'] for r in rules), 'proposed_rules': proposed,
            'non_rule_passages': sum(p['disposition'] == 'NON_RULE' for p in passages),
            'unresolved_passages': unresolved, 'unprocessed_passages': unprocessed,
            'failed_batches': len(record.get('failed_batches', [])) if record else 0,
            'scope_status': (record.get('policy_scope') or {}).get('status','MISSING') if record else 'MISSING',
            'complete': bool(current and record and passages and (record.get('policy_scope') or {}).get('status')=='APPROVED' and not (unprocessed or unresolved or proposed or record.get('failed_batches')))}}
