from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import operator
from fastapi import HTTPException
from ..database import shared_policy_connection, run_db_transaction
from .compliance_agent import GenerativeComplianceReviewAgent

COMPARISONS = {"<=": operator.le, ">=": operator.ge, "==": operator.eq, "!=": operator.ne, "<": operator.lt, ">": operator.gt}

def evaluate(definition, proposal):
    reasons = []
    stage = definition["stage_applicable"]
    if stage.lower() != "all":
        reasons.append(f"Stage: {proposal.get('status')} (required {stage})")
        if proposal.get("status") is None:
            return "Applicable", "WARNING", "Stage is unavailable", None
        if proposal["status"] != stage:
            return "Not applicable", None, "; ".join(reasons), None
    missing = []
    for key, expected in definition.get("applicability", {}).items():
        actual = proposal.get(key)
        reasons.append(f"{key}: {actual} (required {expected})")
        if actual is None:
            missing.append(key)
        elif str(actual) != expected:
            return "Not applicable", None, "; ".join(reasons), None
    if missing:
        return "Applicable", "WARNING", "Applicability cannot be confirmed; missing " + ", ".join(missing), None
    actual = proposal.get(definition["metric"])
    reason = "; ".join(reasons) or "Applies to all requests and stages"
    if actual is None:
        return "Applicable", "WARNING", reason + "; required metric unavailable", None
    threshold = definition["threshold"]
    try:
        left, right = actual, threshold
        if isinstance(threshold, (float, int)):
            left, right = Decimal(str(actual)), Decimal(str(threshold))
            if not left.is_finite() or not right.is_finite():
                raise ValueError("Non-finite metric")
        passed = COMPARISONS[definition["operator"]](left, right)
    except (InvalidOperation, ValueError, TypeError):
        return "Applicable", "WARNING", reason + "; metric cannot be evaluated", actual
    return "Applicable", "PASS" if passed else definition["severity"], reason, actual

def assessment_request_context(request_number,user=None):
    from .assessment_request import normalize_request_id,deal_assessment_context
    request_number=normalize_request_id(request_number)
    is_local=request_number.startswith('CR-')
    if is_local:
        proposal,_,_=GenerativeComplianceReviewAgent._context(request_number)
        proposal['currency']='USD'  # Existing CPI synthetic monetary model is explicitly USD.
    else:
        if user is None:raise HTTPException(401,'Authentication required for Dossier requests')
        proposal=deal_assessment_context(request_number,user)
    if proposal.get('evidence') is None:proposal['evidence']=[]
    from .credit_data import load_record, project_record, ALIASES
    record=load_record(request_number)
    if record:
        for alias in ALIASES: proposal.pop(alias,None)
        proposal.pop('synthetic_fields',None)
        proposal.update(project_record(record))
        proposal['_canonical_record']=record
    return request_number,proposal


def active_rule_candidates(evaluation_date=None):
    from .policy_ingestion import reconcile_policy_sources
    reconcile_policy_sources()
    with shared_policy_connection() as c:
        return c.execute("""SELECT r.*,p.title,p.policy_type,p.library_policy_id,doc.file_name,
            e.rule_code,cl.section_heading,cl.clause_number,cl.page_number,cl.source_excerpt,
            cl.document_id,pv.checksum,pv.effective_date AS policy_effective_from
            FROM policy_rule_versions r JOIN policy_documents p USING(policy_id)
            JOIN policy_versions pv ON pv.id=r.policy_version_id
            JOIN policy_rule_entities e ON e.id=r.rule_entity_id
            JOIN policy_clauses cl ON cl.id=r.clause_id
            JOIN inventory_documents doc ON doc.id=cl.document_id
            WHERE credit_data.is_quantitative_rule(r.definition)
                AND pv.is_current AND r.policy_version=p.version AND r.policy_fingerprint=md5(p.summary)
                AND (%s::date IS NULL OR (r.effective_from<=%s AND (r.effective_to IS NULL OR r.effective_to>=%s) AND pv.effective_date<=%s))
                AND NOT EXISTS (SELECT 1 FROM policy_rule_versions newer
                    WHERE newer.rule_key=r.rule_key AND newer.version>r.version
                    AND newer.policy_version_id=r.policy_version_id)
            ORDER BY r.id""",(evaluation_date,evaluation_date,evaluation_date,evaluation_date)).fetchall()


def run_rule_assessment(request_number,user_id,*,user=None):
    from .request_applicability import RequestApplicabilityAgent
    from .rule_explanation import explain_findings
    from .rule_engine import ENGINE_VERSION, execute_rule
    from .rule_expectation import expected_condition
    request_number,proposal=assessment_request_context(request_number,user)
    is_local=request_number.startswith('CR-')
    now=datetime.now(timezone.utc)
    rules=active_rule_candidates(now.date())
    if not rules:raise HTTPException(409,'No current rule versions are effective. Generate rules in the Policy Rule Library and check their source versions and effective dates.')
    from .policy_scope import policy_first_applicability
    applicability_report=policy_first_applicability(proposal,rules,proposal.get('status'),now.date())
    applicable_ids={d['candidate_id'] for d in applicability_report['decisions']
                    if d['candidate_type']=='Rule' and (d['applicability']=='Applicable' or proposal.get('_canonical_record') and d['applicability']=='Unable to Determine')}
    applicable_rules=[rule for rule in rules if str(rule['id']) in applicable_ids]
    findings=[];snapshots=[]
    for rule in applicable_rules:
        d=rule['definition']
        from .credit_data import resolve_actual
        record=proposal.get('_canonical_record')
        resolution=resolve_actual(rule,record,as_of=now.date()) if record else None
        evaluation=resolution['evaluation'] if resolution else execute_rule(d,proposal,now.date())
        evidence=[{'key':'policy_clause','source':rule['file_name'],'reference':f"document:{rule['document_id']}/clause:{rule['clause_id']}",'value':d['source_excerpt'],'checksum':rule['checksum']}]
        evidence.extend({'key':field,'source':proposal.get('data_source') or 'CPI stored request data','reference':f'request:{request_number}/field:{field}','value':value} for field,value in evaluation['input_values'].items())
        evidence.extend(item for item in proposal['evidence'] if isinstance(item,dict) and item.get('key') in {req['key'] for req in d.get('evidence_requirements',[])})
        if resolution:
            from .credit_data import provenance_sources
            evidence.extend({'key':p['attribute_name'],'source':p['source_type'],'reference':p.get('source_identifier'),'value':p['value'],'provenance':p} for p in resolution['provenance'])
        f={**evaluation,'policy_id':rule['policy_id'],'policy_version_id':rule['policy_version_id'],'policy_version':rule['policy_version'],'policy_name':rule['title'],'policy_type':rule['policy_type'],
           'rule_id':rule['rule_entity_id'],'rule_version_id':rule['id'],'rule_version':rule['version'],'rule_code':rule['rule_code'],'clause_id':rule['clause_id'],
           'source_section':rule['section_heading'],'source_clause':rule['clause_number'],'source_page':rule['page_number'],'source_document_id':rule['document_id'],
           'rule_name':d['rule_name'],'check_question':d.get('check_question'),'operator':d.get('operator'),'threshold_unit':d.get('threshold_unit'),'approval_or_escalation_requirement':d.get('approval_or_escalation_requirement'),'workflow_stage':proposal.get('status'),'request_id':request_number,'evaluated_at':now.isoformat(),
           'rule_type':d.get('rule_type'),'synthetic_inputs':[key for key in evaluation['input_values'] if key in proposal.get('synthetic_fields',[])],
           'evidence':d['source_excerpt'],'evidence_references':evidence,'data_source':d.get('data_source'),
           'actual':str(evaluation['observed_value']) if evaluation['observed_value'] is not None else 'Unavailable','threshold':expected_condition(d),'expected_condition':expected_condition(d),
           'policy_clause':d['rule_name'],'rationale':evaluation['applicability_reason'],'evaluated_values':evaluation['input_values']}
        findings.append(f);snapshots.append(dict(rule))
        if resolution:
            f['actual_data_resolution']={k:v for k,v in resolution.items() if k not in ('evaluation','engine_data')}
            f['actual_unit']=resolution['unit']
            f['actual_sources']=sorted({source for p in resolution['provenance'] for source in provenance_sources(p)})
            f['policy_expected_data_source']=d.get('data_source')
            f['data_source']=', '.join(f['actual_sources'])
            f['synthetic_inputs']=[item['rule_field'] for item in resolution['resolved_fields'] if 'SYNTHETIC' in provenance_sources(item['provenance'])]
    # Related independently tested conditions retain three-valued AND/OR outcomes.
    with shared_policy_connection() as c:
        relationships=c.execute("SELECT * FROM rule_relationships WHERE rule_version_id=ANY(%s) AND relationship_type IN ('AND','OR')",([f['rule_version_id'] for f in findings],)).fetchall()
    by_id={f['rule_version_id']:f for f in findings}
    # Resolve related checks from immutable atomic results, without iteration-order effects.
    atomic={f['rule_version_id']:f['result'] for f in findings}
    for f in findings:
        deps=[rel for rel in relationships if rel['rule_version_id']==f['rule_version_id']]
        f['dependencies']=[dict(rel) for rel in deps]
        for operator_name in ('AND','OR'):
            group=[rel for rel in deps if rel['relationship_type']==operator_name]
            if not group:continue
            results=[atomic[f['rule_version_id']]]+[atomic.get(rel['related_rule_version_id'],'Unable to Assess') for rel in group]
            unknown=any(r in ('Unable to Assess','Manual Review Required','Not Applicable') for r in results)
            failing=any(r in ('Breach','Warning') for r in results)
            passing=any(r=='Pass' for r in results)
            if operator_name=='AND':
                combined='Breach' if 'Breach' in results else 'Warning' if 'Warning' in results else 'Manual Review Required' if unknown else 'Pass'
            else:
                combined='Pass' if passing else 'Manual Review Required' if unknown else 'Breach' if 'Breach' in results else 'Warning'
            f['atomic_result']=atomic[f['rule_version_id']]
            f['result']=combined
            f['severity']={'Pass':'PASS','Warning':'WARNING','Breach':'BREACH'}.get(combined)
            if unknown and combined=='Manual Review Required':f['missing_inputs'].append('Unresolved '+operator_name+' requirement')
            f['applicability_reason']+='; '+operator_name+' dependency outcomes: '+', '.join(results)
    explain_findings(findings)
    counts={status:sum(f.get('severity')==status for f in findings) for status in ('PASS','WARNING','BREACH')}
    outcomes={status:sum(f['result']==status for f in findings) for status in ('Pass','Warning','Breach','Not Applicable','Unable to Assess','Manual Review Required')}
    assessed=sum(counts.values());unknown=outcomes['Unable to Assess']+outcomes['Manual Review Required']
    rank={'PASS':0,'WARNING':1,'BREACH':2};heat={}
    for f in findings:
        if f.get('severity') and rank[f['severity']]>=rank.get(heat.get(f['policy_type']),-1):heat[f['policy_type']]=f['severity']
    result={'agent':'Policy Rule Assessment','assessment_scope':'policy-first-applicable-only','credit_request':proposal,'findings':findings,'applicability':findings,'rule_snapshots':snapshots,'counts':counts,'outcome_counts':outcomes,
            'heatmap':[{'policy_type':k,'severity':v} for k,v in heat.items()],
            'overall_score':None if unknown or not assessed else round(100*counts['PASS']/assessed),
            'compliance_status':'BREACH' if counts['BREACH'] else 'Incomplete assessment' if unknown else 'WARNING' if counts['WARNING'] else 'PASS' if assessed else 'Not Applicable',
            'executive_summary':f"{assessed} checks resolved; {unknown} require data or manual review. Policy scope was checked first; only applicable rules within applicable policies were evaluated.",
            'evaluated_at':now.isoformat(),'engine_version':ENGINE_VERSION,'recommendations':[],'cached':False}
    result['applicability_report']=applicability_report
    serialized=json.dumps(result,default=str)
    def persist(c):
        stored=c.execute('INSERT INTO ai_compliance_reviews(credit_request_number,source_request_id,agent_id,review,created_by) VALUES (%s,%s,%s,%s::jsonb,%s) RETURNING review_id',(request_number if is_local else None,request_number,'approved-rule-library',serialized,user_id)).fetchone()
        run=c.execute('INSERT INTO rule_assessment_runs(review_id,request_id,workflow_stage,engine_version) VALUES (%s,%s,%s,%s) RETURNING id',(stored['review_id'],request_number,proposal.get('status'),ENGINE_VERSION)).fetchone()
        from .request_applicability import RequestApplicabilityAgent
        policies={}
        for f in findings:policies.setdefault(f['policy_version_id'],[]).append(f)
        for pv,group in policies.items():
            applicability,reason=RequestApplicabilityAgent.policy_mapping(group)
            c.execute('INSERT INTO policy_request_mappings(run_id,request_id,policy_id,policy_version_id,applicability,reason) VALUES (%s,%s,%s,%s,%s,%s)',(run['id'],request_number,group[0]['policy_id'],pv,applicability,reason))
        for f in findings:
            row=c.execute("""INSERT INTO request_rule_assessments(run_id,request_id,rule_version_id,policy_version_id,policy_id,rule_id,clause_id,workflow_stage,applicability,input_values,expected_threshold,formula,observed_value,variance,result,severity,evidence_references,missing_inputs,explanation,evaluated_at,engine_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s) RETURNING id""",
                (run['id'],request_number,f['rule_version_id'],f['policy_version_id'],f['policy_id'],f['rule_id'],f['clause_id'],f['workflow_stage'],f['applicability'],json.dumps(f['input_values'],default=str),json.dumps(f['expected_threshold'],default=str),json.dumps(f['formula'],default=str),json.dumps(f['observed_value'],default=str),f['variance'],f['result'],f['severity'],json.dumps(f['evidence_references'],default=str),json.dumps(f['missing_inputs']),f['explanation'],now,ENGINE_VERSION)).fetchone()
            for evidence in f['evidence_references']:
                c.execute('INSERT INTO assessment_evidence(assessment_id,evidence_key,source,observed_value,source_reference,conflicting) VALUES (%s,%s,%s,%s::jsonb,%s,%s)',(row['id'],evidence.get('key','unknown'),evidence.get('source') or 'Request data',json.dumps(evidence.get('value'),default=str),evidence.get('reference'),bool(evidence.get('conflicting'))))
        return stored
    stored=run_db_transaction(persist)
    result=json.loads(serialized);result['review_id']=stored['review_id']
    return result
