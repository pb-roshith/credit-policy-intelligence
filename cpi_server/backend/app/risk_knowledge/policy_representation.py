"""Build a source-backed policy graph, then compile rules by directed traversal."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import networkx as nx
from ..services.inventory_schema import ProposedRule
from .policy_grammar import GRAMMAR_VERSION, RequirementFrame, parse_requirements, sentence_spans, is_non_rule,validate_frame_source,classify_non_rule
from .policy_ontology import ONTOLOGY_VERSION, METRICS, DOCUMENTS, PREDICATES,ontology_contract

REPRESENTATION_VERSION = 'policy-representation-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def representation_id(version_id, checksum):
    return f'POLICY-REPRESENTATION-{version_id}-' + digest([checksum,GRAMMAR_VERSION,ONTOLOGY_VERSION,ontology_contract()])[:16]


def current_representations(records,versions):
    identifiers={representation_id(v['id'],v['checksum']) for v in versions}
    return [r for r in records if r.get('kind')=='policy_representation' and r['id'] in identifiers]


def source_provenance(policy, version, clause, quote):
    return {'document_id':'CPI-POLICY-'+str(policy['policy_id']), 'document_name':policy['title'],
            'origin':'POLICY_SOURCE_REPRESENTATION','version':version['version'],
            'passage':quote,'page':clause.get('page_number'),'section':clause.get('section_heading'),
            'clause':clause.get('clause_number')}


def build_representation(policy,version,document,clauses,concepts=()):
    checksum=document['checksum']
    identifier=representation_id(version['id'],checksum)
    result={'kind':'policy_representation','id':identifier,'representation_version':REPRESENTATION_VERSION,
            'grammar_version':GRAMMAR_VERSION,'ontology_version':ONTOLOGY_VERSION,
            'ontology_digest':digest(ontology_contract()),'ontology_contract':deepcopy(ontology_contract()),
            'policy_id':policy['policy_id'],'policy_version_id':version['id'],'source_checksum':checksum,
            'source_digest':digest([(c['id'],c['source_excerpt']) for c in clauses]),
            'policy_title':policy['title'],'policy_version':version['version'],
            'effective_from':str(version['effective_date']) if version.get('effective_date') else None,
            'source_clauses':deepcopy(clauses),'nodes':[],'edges':[],'coverage':[],
            'fallback':{'attempted':0,'proposals':0,'failures':[]},'reviews':[]}
    root='CPI-POLICY-'+str(policy['policy_id'])
    result['nodes'].append({'id':root,'type':'PolicyDocument','label':policy['title'],'status':'SOURCE',
                            'payload':{'version_id':version['id'],'checksum':checksum},
                            'provenance':{'document_id':root,'document_name':policy['title'],'origin':'POLICY_SOURCE_REPRESENTATION','passage':policy['title'],'version':version['version']}})
    for clause in clauses:
        for start,end,quote in sentence_spans(clause['source_excerpt']):
            sid=identifier+f':span:{clause["id"]}:{start}:{end}'
            frames,reason=parse_requirements(quote)
            classification=None if frames else classify_non_rule(quote)
            status='VALIDATED' if frames else 'NON_RULE' if classification else 'UNRESOLVED'
            provenance=source_provenance(policy,version,clause,quote)
            result['nodes'].append({'id':sid,'type':'SourceSpan','label':quote[:100],
                                    'status':status,'payload':{'clause_id':clause['id'],'start':start,'end':end,'quote':quote},'provenance':provenance})
            add_edge(result,root,'CONTAINS',sid,provenance)
            coverage={'span_id':sid,'clause_id':clause['id'],'start':start,'end':end,'status':status,
                      'reason':None if frames else classification['reason'] if classification else reason,'requirement_ids':[],
                      'classification':classification['category'] if classification else None}
            result['coverage'].append(coverage)
            for index,frame in enumerate(frames):
                rid=add_requirement(result,sid,frame,'GRAMMAR','VALIDATED',concepts,slot=index)
                coverage['requirement_ids'].append(rid)
    seal(result)
    return result


def add_edge(rep,source,predicate,target,provenance,status='SOURCE'):
    rep['edges'].append({'id':'REP-EDGE-'+digest([source,predicate,target])[:24],
                         'source':source,'target':target,'predicate':predicate,
                         'status':status,'provenance':deepcopy(provenance)})


def add_requirement(rep,span_id,frame,origin,status,concepts=(),approval=None,slot=None,logical_key=None,previous_node_ids=()):
    frame=RequirementFrame.model_validate(frame).model_dump(mode='json')
    span=next(n for n in rep['nodes'] if n['id']==span_id and n['type']=='SourceSpan')
    rid=span_id+':requirement:'+digest(frame)[:16]
    source=span['provenance']
    from .rule_identity import source_slot
    if slot is None:slot=sum(n['type']=='PolicyRequirement' and n['id'].startswith(span_id+':requirement:') for n in rep['nodes'])
    logical_key=logical_key or source_slot(rep,span_id,slot)
    rep['nodes'].append({'id':rid,'type':'PolicyRequirement','label':METRICS[frame['metric']]['label'] if frame['metric'] else 'Required '+frame['document'],
                         'status':status,'payload':{'origin':origin,'approval':approval,'logical_rule_key':logical_key,
                                                    'previous_node_ids':list(previous_node_ids)},'provenance':deepcopy(source)})
    add_edge(rep,rid,'DERIVED_FROM',span_id,source,status)
    def component(kind,predicate,suffix,payload,label):
        nid=rid+':'+suffix
        rep['nodes'].append({'id':nid,'type':kind,'label':label,'status':status,'payload':payload,'provenance':deepcopy(source)})
        add_edge(rep,rid,predicate,nid,source,status)
        return nid
    if frame['metric']:
        metric=METRICS[frame['metric']]
        mid=component('PolicyMetric','USES_METRIC','metric',{'key':frame['metric'],'field':metric['field'],'ontology_version':ONTOLOGY_VERSION},metric['label'])
        # Exact source-schema labels only. Do not fuzzy-map e.g. debt service to income.
        names={metric['label'].casefold(),*map(str.casefold,metric['terms'])}
        for concept in concepts:
            if (concept.get('kind')=='ATTRIBUTE' and concept.get('source',{}).get('origin')=='SOURCE_SCHEMA'
                    and concept['preferred_name'].casefold() in names
                    and concept.get('metadata',{}).get('source_entity') in metric.get('taxonomy_entities',[])):
                cid=concept['concept_id']
                if not any(n['id']==cid for n in rep['nodes']):
                    rep['nodes'].append({'id':cid,'type':'ATTRIBUTE','label':concept['preferred_name'],'status':concept['status'],
                                         'payload':deepcopy(concept),'provenance':deepcopy(concept['source'])})
                add_edge(rep,mid,'MAPS_TO',cid,concept['source'],status)
    else:
        component('PolicyDocumentType','REQUIRES_DOCUMENT','document',{'key':frame['document']},frame['document'])
    component('PolicyConstraint','CONSTRAINS','constraint',{'operator':frame['operator'],'threshold':frame['threshold'],'unit':frame['unit']},str(frame['threshold'])+' '+str(frame['unit'] or ''))
    for key,predicate in (('scope','HAS_SCOPE'),('exclusions','HAS_EXCEPTION')):
        if frame[key]:component('PolicyCondition',predicate,key,frame[key],key)
    return rid


def graph_from_representation(rep):
    if rep['representation_version']!=REPRESENTATION_VERSION or rep['ontology_version']!=ONTOLOGY_VERSION or rep['grammar_version']!=GRAMMAR_VERSION:
        raise ValueError('Unsupported policy representation/ontology/grammar version')
    if rep.get('ontology_digest')!=digest(ontology_contract()) or digest(rep.get('ontology_contract'))!=rep['ontology_digest']:
        raise ValueError('Policy ontology changed; rebuild the source representation')
    graph=nx.DiGraph()
    for node in rep['nodes']:
        if node['id'] in graph:raise ValueError('Duplicate representation node')
        graph.add_node(node['id'],**deepcopy(node))
    edge_ids=set()
    for edge in rep['edges']:
        a,b=edge['source'],edge['target']
        if a not in graph or b not in graph or edge['predicate'] not in PREDICATES or edge['id'] in edge_ids:
            raise ValueError('Unknown graph endpoint, predicate or duplicate edge')
        if (graph.nodes[a]['type'],graph.nodes[b]['type'])!=PREDICATES[edge['predicate']] or not edge.get('provenance'):
            raise ValueError('Relationship violates the policy ontology')
        if graph.has_edge(a,b):raise ValueError('Ambiguous parallel representation edges')
        graph.add_edge(a,b,**deepcopy(edge));edge_ids.add(edge['id'])
    if not nx.is_directed_acyclic_graph(graph):raise ValueError('Policy representation must be acyclic')
    return graph


def frame_from_graph(graph,rid):
    """Read semantics from typed edges, not a previously generated rule payload."""
    values={}
    targets={}
    for _,target,edge in graph.out_edges(rid,data=True):targets.setdefault(edge['predicate'],[]).append(target)
    for predicate in ('DERIVED_FROM','CONSTRAINS'):
        if len(targets.get(predicate,[]))!=1:raise ValueError('A requirement needs exactly one '+predicate)
    for predicate in ('USES_METRIC','REQUIRES_DOCUMENT','HAS_SCOPE','HAS_EXCEPTION'):
        if len(targets.get(predicate,[]))>1:raise ValueError('Ambiguous requirement component')
    values.update(graph.nodes[targets['CONSTRAINS'][0]]['payload'])
    if targets.get('USES_METRIC'):
        node=graph.nodes[targets['USES_METRIC'][0]]['payload'];key=node['key']
        if key not in METRICS or node['field']!=METRICS[key]['field'] or node['ontology_version']!=ONTOLOGY_VERSION:
            raise ValueError('Metric binding differs from the versioned ontology')
        values['metric']=key
    if targets.get('REQUIRES_DOCUMENT'):values['document']=graph.nodes[targets['REQUIRES_DOCUMENT'][0]]['payload']['key']
    for predicate,key in (('HAS_SCOPE','scope'),('HAS_EXCEPTION','exclusions')):
        if targets.get(predicate):values[key]=graph.nodes[targets[predicate][0]]['payload']
    return RequirementFrame.model_validate(values),targets['DERIVED_FROM'][0]


def seal(rep):
    rep['content_digest']=digest({k:v for k,v in rep.items() if k!='content_digest'})


def validate_coverage(rep,graph,clauses):
    expected={(c['id'],start,end):quote for c in clauses for start,end,quote in sentence_spans(c['source_excerpt'])}
    seen=set();covered_requirements=set()
    for row in rep['coverage']:
        key=(row['clause_id'],row['start'],row['end'])
        if key in seen or key not in expected:raise ValueError('Duplicate or unknown source coverage span')
        seen.add(key)
        sid=row['span_id']
        if sid not in graph or graph.nodes[sid]['type']!='SourceSpan':raise ValueError('Source coverage node is missing')
        payload=graph.nodes[sid]['payload']
        if (payload['clause_id'],payload['start'],payload['end'],payload['quote'])!=(*key,expected[key]):
            raise ValueError('Source coverage offsets or quotation changed')
        parsed,_=parse_requirements(expected[key])
        if row['status']=='VALIDATED':
            if not parsed or len(row['requirement_ids'])!=len(parsed):raise ValueError('Validated source span lost its complete grammar interpretation')
        elif row['status']=='NON_RULE':
            reviewed=any(r['span_id']==sid and r['disposition']=='NON_RULE' and r.get('reviewer') and r.get('source_checksum')==rep['source_checksum'] for r in rep['reviews'])
            if row['requirement_ids'] or not (is_non_rule(expected[key]) or reviewed):raise ValueError('Non-rule disposition needs metadata recognition or explicit source review')
        elif row['status'] not in ('UNRESOLVED','LLM_PROPOSED','REVIEWED'):
            raise ValueError('Unknown source coverage disposition')
        if row['status']=='REVIEWED' and not row['requirement_ids']:raise ValueError('Reviewed requirement has no interpretation')
        if row['status']=='UNRESOLVED' and row['requirement_ids']:raise ValueError('Unresolved source cannot carry executable interpretations')
        actual_frames=[]
        for rid in row['requirement_ids']:
            if rid in covered_requirements or rid not in graph or graph.nodes[rid]['type']!='PolicyRequirement':
                raise ValueError('Requirement is missing or assigned to multiple source spans')
            covered_requirements.add(rid)
            frame,source=frame_from_graph(graph,rid)
            actual_frames.append(frame.model_dump(mode='json'))
            if source!=sid:raise ValueError('Coverage requirement references another source span')
            if row['status']=='VALIDATED' and (graph.nodes[rid]['payload']['origin']!='GRAMMAR' or graph.nodes[rid]['status']!='VALIDATED'):
                raise ValueError('Grammar coverage differs from its source interpretation')
            if row['status']=='LLM_PROPOSED' and graph.nodes[rid]['status']!='PROPOSED':raise ValueError('Unreviewed source proposal cannot become executable')
            if row['status']=='REVIEWED' and graph.nodes[rid]['status']!='APPROVED':raise ValueError('Reviewed source interpretation lacks approval')
        if row['status']=='VALIDATED' and sorted(map(digest,actual_frames))!=sorted(digest(f.model_dump(mode='json')) for f in parsed):
            raise ValueError('Grammar coverage lost or altered a source requirement branch')
    if seen!=set(expected):raise ValueError('Source coverage omitted a passage')
    if covered_requirements!={rid for rid,n in graph.nodes(data=True) if n['type']=='PolicyRequirement'}:
        raise ValueError('Graph requirement is not accounted for by source coverage')


def compile_graph(rep,clauses):
    """Fail closed on altered source, unsupported semantics or unreviewed proposals."""
    if rep.get('content_digest')!=digest({k:v for k,v in rep.items() if k!='content_digest'}):
        raise ValueError('Policy representation integrity check failed')
    if rep['source_digest']!=digest([(c['id'],c['source_excerpt']) for c in clauses]):
        raise ValueError('Policy source changed; rebuild the representation')
    by_clause={c['id']:c for c in clauses}
    graph=graph_from_representation(rep)
    validate_coverage(rep,graph,clauses)
    result=[];sequences={}
    requirements=[(rid,node) for rid,node in graph.nodes(data=True) if node['type']=='PolicyRequirement']
    def order(item):
        _,sid=frame_from_graph(graph,item[0])
        span=graph.nodes[sid]['payload']
        return (list(by_clause).index(span['clause_id']),span['start'],item[0])
    for rid,node in sorted(requirements,key=order):
        if node['type']!='PolicyRequirement' or node['status'] not in ('VALIDATED','APPROVED'):continue
        frame,sid=frame_from_graph(graph,rid)
        span=graph.nodes[sid]['payload'];clause=by_clause.get(span['clause_id'])
        if not clause or clause['source_excerpt'][span['start']:span['end']]!=span['quote']:
            raise ValueError('Source offsets do not identify the exact supporting passage')
        provenance=graph.nodes[sid].get('provenance') or {}
        if provenance.get('passage')!=span['quote'] or provenance.get('document_id')!='CPI-POLICY-'+str(rep['policy_id']) or provenance.get('version')!=rep['policy_version']:
            raise ValueError('Source span provenance does not match the policy version')
        for _,target,edge in graph.out_edges(rid,data=True):
            if graph.nodes[target].get('provenance')!=provenance or edge.get('provenance')!=provenance:
                raise ValueError('Requirement component provenance differs from its supporting span')
        root='CPI-POLICY-'+str(rep['policy_id'])
        if not graph.has_edge(root,sid) or graph[root][sid]['predicate']!='CONTAINS':
            raise ValueError('Requirement is not reachable from its policy source')
        payload=node['payload']
        validate_frame_source(frame,span['quote'])
        if payload['origin']=='GRAMMAR':
            parsed,_=parse_requirements(span['quote'])
            if not any(p.model_dump()==frame.model_dump() for p in parsed):
                raise ValueError('Graph semantics differ from the complete source grammar match')
        else:
            approval=payload.get('approval') or {}
            if node['status']!='APPROVED' or not approval.get('reviewer') or approval.get('frame_digest')!=digest(frame.model_dump(mode='json')) or approval.get('source_checksum')!=rep['source_checksum']:
                raise ValueError('Fallback interpretation requires explicit version-bound human approval')
        cid=clause['id'];sequences[cid]=sequences.get(cid,0)+1
        metric=METRICS.get(frame.metric,{})
        fields=[metric['field']] if frame.metric else ['documents']
        label=metric.get('label') or 'Required '+frame.document
        from .rule_identity import source_slot,semantic_digest
        coverage=next(c for c in rep['coverage'] if c['span_id']==sid)
        logical_key=payload.get('logical_rule_key') or source_slot(rep,sid,coverage['requirement_ids'].index(rid))
        def describe_scope(condition):
            if not condition:return ''
            group=condition.all or condition.any
            if group:return '('+(' AND ' if condition.all else ' OR ').join(describe_scope(c) for c in group)+')'
            op={'equals':'','greater_than_or_equal':'>= ','less_than':'< '}.get(condition.operator,condition.operator+' ')
            return op+str(condition.value)
        title=label+' '+frame.operator+' '+str(frame.threshold)+(frame.unit or '')
        if frame.scope:title+=' | '+describe_scope(frame.scope)
        rule=ProposedRule(clause_id=cid,rule_sequence=sequences[cid],rule_name=title[:200],
            rule_description=span['quote'],source_excerpt=span['quote'],requirement_kind='mandatory',
            rule_type='quantitative' if frame.metric else 'documentary',check_question='Does the request satisfy: '+span['quote'][:1900],
            metric_name=label,operator=frame.operator,threshold_value=frame.threshold,threshold_unit=frame.unit,
            severity=(payload.get('approval') or {}).get('operational_severity'),
            threshold_source=span['quote'] if frame.metric else None,
            calculation_logic={'method':'direct','field':metric['field']} if frame.metric else {'method':'document_presence','document_key':frame.document},
            input_data_fields=fields,evidence_requirements=[],applicability_conditions=frame.scope,
            applicability_exclusions=frame.exclusions,extraction_confidence=1.0 if payload['origin']=='GRAMMAR' else 0.0,
            extraction_notes='Compiled by directed traversal of '+rid,missing_information=['Operational severity requires reviewer assignment'],
            mandatory=True,representation_id=rep['id'],representation_node_id=rid,
            representation_digest=rep['content_digest'],representation_version=REPRESENTATION_VERSION)
        rule.representation_rule_key=logical_key
        rule.requirement_digest=semantic_digest(rule.model_dump(mode='json'))
        result.append(rule)
    return result


def coverage_summary(rep):
    counts={status:sum(c['status']==status for c in rep['coverage']) for status in ('VALIDATED','REVIEWED','NON_RULE','UNRESOLVED','LLM_PROPOSED')}
    counts['total_spans']=len(rep['coverage'])
    counts['unresolved_spans']=counts['UNRESOLVED']+counts['LLM_PROPOSED']
    counts['complete']=counts['unresolved_spans']==0
    return counts


def project_representations(graph,representations,rules=()):
    snapshot=graph.snapshot()
    nodes={n['id']:n for n in snapshot['nodes']};edges={e['id']:e for e in snapshot['edges']}
    for rep in representations:
        for node in rep['nodes']:
            if node['id'] not in nodes:
                nodes[node['id']]={**deepcopy(node),'risk_domain':'Credit Risk',
                                   'source_name':node['provenance']['document_name']}
        for edge in rep['edges']:edges[edge['id']]=deepcopy(edge)
    for rule in rules:
        definition=rule['definition'];rid='CPI-RULE-'+str(rule['id']);target=definition.get('representation_node_id')
        if rid in nodes and target in nodes:
            source=nodes[target]['provenance']
            eid='REP-COMPILED-'+str(rule['id'])
            edges[eid]={'id':eid,'source':rid,'target':target,'predicate':'COMPILED_FROM',
                         'status':rule['status'].upper(),'provenance':source}
    graph.replace(list(nodes.values()),list(edges.values()))
