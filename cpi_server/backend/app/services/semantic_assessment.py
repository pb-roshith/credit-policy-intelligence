"""Compliance assessment of the same current semantic rules shown in the graph."""
from datetime import datetime, timezone, date
import json
from fastapi import HTTPException
from ..database import run_db_transaction
from .semantic_matching import load_matcher, Facts, converted, comparison, number
from .rule_assessment import assessment_request_context
from .semantic_request_graph import request_overlay

ENGINE_VERSION = 'semantic-graph-assessment-v2'
OPERATORS = {'LTE':'≤','GTE':'≥','LT':'<','GT':'>','EQ':'=','NE':'≠'}


def evaluate_graph_rule(matcher, decision, proposal, *, actual_samples=None, manufacture_qualitative=False, as_of=None):
    rid=decision['candidate_id']; record,row=matcher.rows[rid]; rule=row['extracted']
    facts=Facts(proposal); checks=[]; sources=[]; missing=[]
    for tid in matcher.targets(rid,'HAS_THRESHOLD'):
        boundary=matcher.nodes[tid]['properties']
        for mid in matcher.targets(tid,'MEASURED_BY'):
            metric=matcher.nodes[mid]['properties']; key=metric['metric_key']
            actual,unit,source=facts.get(key)
            if actual is None and source.get('status') in ('MISSING','MISSING_CANONICAL_FACT'):
                from ..manufacture_data.semantic_actuals import sample_key
                sample=(actual_samples or {}).get(sample_key(key,boundary['unit'],proposal.get('currency')))
                if sample:actual,unit,source=sample['value'],sample['unit'],sample
            sources.append(source)
            try:
                value=converted(actual,unit,boundary['unit']) if actual is not None else None
                outcome=comparison(value,boundary['operator'],boundary['value'])
            except (ValueError,TypeError,ArithmeticError):value=None;outcome=None
            try:variance=str(number(value)-number(boundary['value'])) if value is not None else None
            except (ValueError,TypeError,ArithmeticError):variance=None
            if outcome is None:missing.append(key+' (fact and compatible unit required)')
            checks.append({'threshold_node':tid,'metric_node':mid,'metric':key,'actual':float(value) if hasattr(value,'as_tuple') else value,
                'actual_unit':unit,'operator':boundary['operator'],'threshold':boundary['value'],'unit':boundary['unit'],'condition_met':outcome,
                'source_type':source.get('source_type') or source.get('provenance',{}).get('source_type') or 'STORED_REQUEST','variance':variance})
    requirements=[]
    for approval in matcher.targets(rid,'REQUIRES_APPROVAL'):
        authorities=[matcher.nodes[a]['label'] for a in matcher.targets(approval,'REQUIRES_APPROVAL_FROM')]
        requirements.append({'node_id':approval,'type':'approval','authorities':authorities})
    for evidence in matcher.targets(rid,'REQUIRES_EVIDENCE'):
        requirements.append({'node_id':evidence,'type':'evidence','evidence_type':matcher.nodes[evidence]['properties']['evidence_type']})
    # A graph requirement is never evidence that approval was granted. The
    # assessment retains duties for review, without manufacturing supporting data.
    if requirements:missing.extend('Verified '+r['type']+': '+', '.join(r.get('authorities') or [r.get('evidence_type','')]) for r in requirements)
    outcomes=[c['condition_met'] for c in checks]
    result='Breach' if False in outcomes else 'Unable to Assess' if None in outcomes else 'Manual Review Required' if not checks or requirements else 'Pass'
    if not checks:missing.append('Source-backed manual verification of the qualitative requirement')
    if not checks and manufacture_qualitative:
        from ..manufacture_data.semantic_actuals import qualitative_observation
        sources.append(qualitative_observation(proposal.get('credit_request_number') or proposal.get('request_id'),rid,as_of))
    source=matcher.clauses.get(rule['clause_id'],{})
    evidence=[{'key':'policy_clause','source':record['policy_name'],'reference':f"policy-version:{record['policy_version_id']}/clause:{rule['clause_id']}",
        'value':rule['source_quote'],'checksum':record['source_checksum']}]
    evidence.extend({'key':s['field'],'source':s.get('source') or s.get('provenance',{}).get('source_type') or 'Canonical request data',
        'value':s.get('value'),'reference':s.get('source_identifier') or s.get('binding') or s.get('canonical_field'),
        'source_type':s.get('source_type') or s.get('provenance',{}).get('source_type'),'provenance':s} for s in sources)
    expected='; '.join(f"{c['metric']} {OPERATORS[c['operator']]} {c['threshold']} {c['unit']}" for c in checks) or rule['source_quote']
    actual='; '.join(f"{c['metric']}: {c['actual']} {c['unit']}" if c['actual'] is not None else f"{c['metric']}: unavailable" for c in checks) or 'Manual verification required'
    if not checks and manufacture_qualitative:actual=sources[-1]['value']
    category='QUANTITATIVE' if rule['rule_kind']=='QUANTITATIVE' or rule['thresholds'] else 'QUALITATIVE'
    return {'rule_id':rid,'rule_version_id':rid,'rule_version':record['content_digest'],'rule_code':rid,'rule_name':rule['name'],
        'rule_category':category,'rule_kind':rule['rule_kind'],
        'policy_clause':rule['name'],'policy_id':record['policy_id'],'policy_name':record['policy_name'],'policy_type':'Credit Policy',
        'policy_version_id':record['policy_version_id'],'policy_version':record['policy_version'],'clause_id':rule['clause_id'],
        'source_clause':source.get('clause_number') or str(rule['clause_id']),'source_section':source.get('section_heading'),'source_page':source.get('page_number'),
        'evidence':rule['source_quote'],'evidence_references':evidence,'threshold':expected,'expected_condition':expected,
        'actual':actual,'observed_value':checks[0]['actual'] if len(checks)==1 else None,'variance':checks[0]['variance'] if len(checks)==1 else None,
        'operator':checks[0]['operator'] if len(checks)==1 else None,'threshold_unit':checks[0]['unit'] if len(checks)==1 else None,
        'expected_threshold':checks[0]['threshold'] if len(checks)==1 else None,'metric_checks':checks,
        'result':result,'severity':{'Pass':'PASS','Breach':'BREACH'}.get(result),'applicability':'Applicable',
        'applicability_reason':decision['reason'],'rationale':decision['reason'],'matching_trace':decision,
        'input_values':{s['field']:s.get('value') for s in sources},'evaluated_values':{s['field']:s.get('value') for s in sources},
        'missing_inputs':missing,'approval_requirements':requirements,
        'approval_or_escalation_requirement':'; '.join(', '.join(r.get('authorities',[])) for r in requirements if r['type']=='approval') or None,
        'exception_nodes':matcher.targets(rid,'HAS_EXCEPTION'),
        'synthetic_inputs':[s['field'] for s in sources if s.get('source_type')=='SYNTHETIC' or s.get('provenance',{}).get('source_type')=='SYNTHETIC'],
        'actual_sources':sorted({s.get('source_type') or s.get('provenance',{}).get('source_type') or 'STORED_REQUEST' for s in sources}),
        'source_is_synthetic':record['synthetic'],'workflow_stage':proposal.get('status'),
        'explanation':f"{rule['name']}: {result}. Matched through current policy/version/rule graph paths. "+('Missing: '+'; '.join(missing) if missing else 'All measured thresholds satisfy the extracted requirements.')}


def build_assessment(request_id,proposal,matcher,*,evaluation_date=None,manufacture_missing=False):
    today=evaluation_date or date.today();report=matcher.match(proposal,today)
    decisions=[d for d in report['decisions'] if d['candidate_type']=='Rule' and d['applicability']=='Applicable']
    from ..manufacture_data.semantic_actuals import manufacture_actuals,VERSION as ACTUAL_GENERATOR_VERSION
    samples=manufacture_actuals(request_id,proposal,matcher,decisions,today) if manufacture_missing else {}
    findings=[evaluate_graph_rule(matcher,d,proposal,actual_samples=samples,manufacture_qualitative=manufacture_missing,as_of=today) for d in decisions]
    counts={s:sum(f.get('severity')==s for f in findings) for s in ('PASS','WARNING','BREACH')}
    outcomes={s:sum(f['result']==s for f in findings) for s in ('Pass','Warning','Breach','Unable to Assess','Manual Review Required')}
    coverage_pending=any(c['proposed_rules'] or c['unresolved_passages'] or c['failed_batches'] or c['scope_status']!='APPROVED' for c in report['coverage']) or bool(report['missing_extraction_policy_ids'])
    incomplete=bool(report['unresolved_rule_count'] or report['unresolved_policy_count'] or coverage_pending or outcomes['Unable to Assess'] or outcomes['Manual Review Required'])
    summary=(f"Graph traversal checked {report['graph_rule_count']} published rules across {len(matcher.documents)} policies. "
             f"{len(findings)} rules match; {report['excluded_rule_count']} do not match; {report['unresolved_rule_count']} need scope or request information. "
             'The LLM explains retrieved evidence; it does not select rules or determine outcomes.')
    evaluated_at = datetime.now(timezone.utc).isoformat()
    return {'agent':'Knowledge Graph Compliance Assessment','engine_version':ENGINE_VERSION,'assessment_scope':'current-semantic-graph',
        'credit_request':{k:v for k,v in proposal.items() if k!='_canonical_record'},'findings':findings,'applicability':findings,
        'applicability_report':report,'knowledge_fingerprint':matcher.fingerprint,
        'request_graph':request_overlay(request_id,proposal,evaluated_on=today.isoformat(),evaluation_reference=evaluated_at,
                                        findings=findings,rule_nodes=matcher.nodes),
        'rule_snapshots':[{'id':d['candidate_id'],'policy_id':d['policy_id'],'semantic_rule':matcher.rows[d['candidate_id']][1],
                           'content_digest':matcher.rows[d['candidate_id']][0]['content_digest']} for d in decisions],
        'counts':counts,'outcome_counts':outcomes,'overall_score':None if incomplete or not findings else round(100*counts['PASS']/len(findings)),
        'compliance_status':'BREACH' if counts['BREACH'] else 'Incomplete assessment' if incomplete else 'PASS' if findings else 'Not Applicable',
        'executive_summary':summary,'evaluated_at':evaluated_at,'cached':False,'recommendations':[],
        'heatmap':[],'demonstration_data_used':any(f['synthetic_inputs'] for f in findings),'manufactured_inputs':samples,
        'actual_generator_version':ACTUAL_GENERATOR_VERSION if manufacture_missing else None,
        'assessment_mode':'DEMONSTRATION' if any(f['synthetic_inputs'] for f in findings) else 'STORED_REQUEST_FACTS',
        'knowledge_snapshot':{'records':{str(r['policy_id']):r['content_digest'] for r in matcher.records},
            'sources':{str(d['policy_id']):{'version_id':d.get('policy_version_id'),'checksum':d.get('checksum'),'effective_date':str(d.get('effective_date'))} for d in matcher.documents}}}


def run_rule_assessment(request_number,user_id,*,user=None):
    request_id,proposal=assessment_request_context(request_number,user)
    matcher=load_matcher()
    if not matcher.records:raise HTTPException(409,'No current semantic extraction is available. Extract policy rules first.')
    result=build_assessment(request_id,proposal,matcher,manufacture_missing=True)
    from .semantic_rag import explain_assessment
    result['graph_rag_explanation']=explain_assessment(result)
    result['review_id']=run_db_transaction(
        lambda connection: persist_assessment(connection,request_id,result,user_id))
    return json.loads(json.dumps(result,default=str))


def persist_assessment(connection, request_id, result, user_id):
    row=connection.execute('INSERT INTO ai_compliance_reviews(credit_request_number,source_request_id,agent_id,review,created_by) VALUES (%s,%s,%s,%s::jsonb,%s) RETURNING review_id',
        (request_id if request_id.startswith('CR-') else None,request_id,'semantic-graph-assessment',json.dumps(result,default=str),user_id)).fetchone()
    # The immutable JSON snapshot stores semantic decisions and graph traces.
    connection.execute('INSERT INTO rule_assessment_runs(review_id,request_id,workflow_stage,engine_version) VALUES (%s,%s,%s,%s)',
        (row['review_id'],request_id,result['credit_request'].get('status'),ENGINE_VERSION))
    return row['review_id']
