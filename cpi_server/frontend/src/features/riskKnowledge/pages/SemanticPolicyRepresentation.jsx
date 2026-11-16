import React,{useEffect,useRef,useState} from 'react';
import {api,post} from '../services/api';
import {Panel,Badge,Source,Empty} from '../components/ui';
import Graph from '../graph/Graph';
import {filterSemanticPassages,formatExtractedConditions,describeExtractedRequirement} from '../../../api/policyRepresentation';

export default function SemanticPolicyRepresentation({state,run,canReview,canExtract=canReview,onOpenRules}) {
 const policies=[...new Map(state.documents.filter(d=>d.metadata?.existing_policy_id).map(d=>[d.metadata.existing_policy_id,d])).values()];
 const [policyId,setPolicyId]=useState(()=>String(policies.find(p=>String(p.metadata.existing_policy_id)===sessionStorage.getItem('policyEvidencePolicy'))?.metadata.existing_policy_id||policies[0]?.metadata.existing_policy_id||''));
 const [data,setData]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[revision,setRevision]=useState(0);
 const [selected,setSelected]=useState(null),[filter,setFilter]=useState('ALL'),[query,setQuery]=useState(''),[limit,setLimit]=useState(40);
 const [graph,setGraph]=useState(null),[graphNode,setGraphNode]=useState(null),[next,setNext]=useState(null),[back,setBack]=useState([]);
 const [scopeEdit,setScopeEdit]=useState(null),[scopeNotes,setScopeNotes]=useState('');
 const graphRequest=useRef(0);
 useEffect(()=>{
  if(!policyId)return;
  let active=true;const request=++graphRequest.current;
  setScopeEdit(null);setScopeNotes('');setLoading(true);setError('');setData(null);setSelected(null);setGraph(null);setGraphNode(null);setNext(null);setBack([]);setLimit(40);
  api(`/semantic-policies/${policyId}/representation`).then(result=>{
   if(!active)return;setData(result);
   const clause=Number(sessionStorage.getItem('policyEvidenceClause'));
   if(String(result.policy_id)===sessionStorage.getItem('policyEvidencePolicy')&&result.passages.some(p=>p.clause_id===clause))setSelected(clause);
   if(request===graphRequest.current){setGraph(result.graph);setNext(result.graph.next_offset!=null?{focus:result.graph.focus,offset:result.graph.next_offset}:null)}
  }).catch(e=>{if(active)setError(e.message)}).finally(()=>{if(active)setLoading(false)});
  return()=>{active=false;graphRequest.current++};
 },[policyId,revision]);
 async function explore(focus,offset=0){
  const request=++graphRequest.current;setError('');
  try{const result=await api('/semantic-graph?'+new URLSearchParams({focus,offset:String(offset),limit:'6'}));
   if(request!==graphRequest.current)return;
   setBack(history=>[...history,{graph,next}]);setGraph(result);setGraphNode(null);
   setNext(result.next_offset!=null?{focus,offset:result.next_offset}:null);
  }catch(e){if(request===graphRequest.current)setError(e.message)}
 }
 function overview(){graphRequest.current++;setGraph(data.graph);setGraphNode(null);setNext(data.graph.next_offset!=null?{focus:data.graph.focus,offset:data.graph.next_offset}:null);setBack([])}
 function openRules(){sessionStorage.setItem('ruleLibraryPolicy',policyId);onOpenRules()}
 async function extract(){await post('/extractions',{policy_ids:[Number(policyId)]});openRules()}
 async function saveScope(status){
  await post(`/semantic-policies/${policyId}/scope`,{expected_digest:data.record_digest,scope:JSON.parse(scopeEdit),status,notes:scopeNotes});
  setRevision(n=>n+1);
 }
 function selectPassage(passage){setSelected(passage.clause_id);if(data.has_extraction)explore(`urn:cpi:source:${data.policy_version_id}:${passage.clause_id}`)}
 const passage=data?.passages.find(p=>p.clause_id===selected);
 const linkedIds=new Set([...(passage?.primary_rule_ids||[]),...(passage?.supporting_rule_ids||[])]);
 const linkedRules=data?.rules.filter(r=>linkedIds.has(r.id))||[];
 const visible=filterSemanticPassages(data?.passages||[],filter,query);
 return <>
  <Panel title="Policy Evidence" sub="Verify extracted rules against their original policy passages and trace their knowledge graph connections.">
   <div className="toolbar"><label>Policy<select value={policyId} onChange={e=>{setPolicyId(e.target.value);setFilter('ALL');setQuery('')}}>{policies.map(p=><option key={p.metadata.existing_policy_id} value={p.metadata.existing_policy_id}>{p.document_name}</option>)}</select></label>{canExtract&&<button onClick={()=>run(extract,'Current AI rule extraction queued')}>Extract / refresh rules</button>}<button onClick={()=>setRevision(n=>n+1)}>Reload</button><button onClick={openRules}>Review extracted rules</button></div>
   {error&&<p role="alert" className="notice error">{error}</p>}
   {loading&&<p role="status">Loading current source passages and extracted rules…</p>}
   {data&&<>
    <p>{data.policy_name} · Policy version {data.policy_version||'Not ingested'}{data.pipeline?` · ${data.pipeline}`:''}</p>
    <div className="knowledge-counts"><span><b>{data.summary.source_passages}</b> source passages</span><span><b>{data.summary.extracted_rules}</b> AI-extracted rules</span><span><b>{data.summary.published_rules}</b> approved graph rules</span><span><b>{data.summary.proposed_rules}</b> proposed rules</span><span><b>{data.summary.unresolved_passages}</b> unresolved passages</span><span><b>{data.summary.unprocessed_passages}</b> unprocessed passages</span></div>
    {data.source_status!=='CURRENT'&&<p className="notice">The current registered source needs ingestion or a source-version refresh. Extract this policy to read the current registered document.</p>}
    {!data.has_extraction&&data.passages.length>0&&<p className="notice">The source passages are stored and shown below. No matching current AI extraction is available yet.</p>}
    {data.has_extraction&&<p>{data.summary.complete?'Every stored passage has a recorded disposition and no proposed rules remain.':'Extraction coverage or rule review is incomplete. Proposed rules and unresolved/unprocessed passages are retained below.'}</p>}
   </>}
  </Panel>
  {data&&<>
   {data.policy_scope&&<Panel title="Policy applicability scope" sub="Rules inherit these source-backed conditions before their individual applicability is checked.">
    <Badge>{data.policy_scope.status}</Badge><p>Inclusion: {data.policy_scope.unrestricted?'Explicit universal credit scope':formatExtractedConditions(data.policy_scope.conditions)}</p>
    {data.policy_scope.exclusions&&<p>Excluded when: {formatExtractedConditions(data.policy_scope.exclusions)}</p>}
    {data.policy_scope.validation_error&&<p className="notice">{data.policy_scope.validation_error}</p>}
    <details><summary>Scope source evidence</summary>{data.policy_scope.sources.map((citation,i)=><blockquote key={i}>Passage {citation.clause_id}: {citation.quote}</blockquote>)}</details>
    {canReview&&<><button onClick={()=>setScopeEdit(JSON.stringify(Object.fromEntries(['sources','conditions','exclusions','unrestricted','unresolved_reason'].map(k=>[k,data.policy_scope[k]])),null,2))}>Review / override scope</button>{scopeEdit!==null&&<><label>Source-backed scope<textarea rows="16" value={scopeEdit} onChange={e=>setScopeEdit(e.target.value)}/></label><label>Review rationale<textarea value={scopeNotes} onChange={e=>setScopeNotes(e.target.value)}/></label><button disabled={scopeNotes.trim().length<3} onClick={()=>run(()=>saveScope('APPROVED'),'Policy scope approved')}>Save approved scope</button><button disabled={scopeNotes.trim().length<3} onClick={()=>run(()=>saveScope('PROPOSED'),'Scope returned for correction')}>Return scope for correction</button></>}</>}
   </Panel>}
   <Panel title="Source passages" sub={`${visible.length} of ${data.passages.length} passages in this view. Select a passage to inspect its exact text and linked rules.`}>
    <div className="toolbar"><label>Show<select value={filter} onChange={e=>{setFilter(e.target.value);setLimit(40)}}><option value="ALL">All passages</option><option value="RULES">Passages linked to rules</option><option value="UNRESOLVED">Needs interpretation</option><option value="NON_RULE">Background / source structure</option><option value="NOT_PROCESSED">Not processed</option></select></label><label>Search source<input value={query} onChange={e=>{setQuery(e.target.value);setLimit(40)}}/></label></div>
    <div className="representation-passages">{visible.slice(0,limit).map(p=><button key={p.clause_id} className={selected===p.clause_id?'selected':''} onClick={()=>selectPassage(p)}><Badge>{p.disposition}</Badge><span>{p.source.passage}</span><small>Passage {p.sequence} · {p.source.page?`Page ${p.source.page} · `:''}{p.primary_rule_ids.length} primary rules · {p.supporting_rule_ids.length} supporting links · {p.reason}</small></button>)}</div>
    {visible.length>limit&&<button onClick={()=>setLimit(n=>n+40)}>Show 40 more passages</button>}
    {!visible.length&&<Empty>{data.passages.length?'No passages match these filters. Choose All passages or clear the search.':'No current source passages are stored. Extract this policy to ingest its registered source document.'}</Empty>}
   </Panel>
   {passage&&<Panel title={`Source passage ${passage.sequence}`} action={<Badge>{passage.disposition}</Badge>}>
    <Source source={passage.source}/><p>{passage.reason}</p>
    <h3>Linked extracted rules ({linkedRules.length})</h3>
    {linkedRules.map(rule=><article key={rule.id}><h3>{rule.extracted.name}</h3><p><Badge>{rule.status}</Badge> · {passage.primary_rule_ids.includes(rule.id)?'Primary source passage':'Supporting policy context'} · {rule.published_in_graph?'Published in graph':'Awaiting publication or review'}</p>
     <p>{describeExtractedRequirement(rule.extracted)}</p><p>Applies when: {formatExtractedConditions(rule.extracted.conditions)}</p>
     <p>Products: {rule.extracted.products.map(v=>v.name).join(', ')||'Not stated'} · Customer segments: {rule.extracted.customer_segments.map(v=>v.name).join(', ')||'Not stated'}</p>
     {rule.extracted.approvals.length>0&&<p>Approval / escalation: {rule.extracted.approvals.map(a=>a.name).join(', ')}</p>}
     {rule.extracted.base_rule_ref&&<p>Exception reference: {rule.extracted.base_rule_ref}</p>}
     {rule.validation_error&&<p className="notice">{rule.validation_error}</p>}
     {(!rule.source_quote_verified||!rule.supporting_quotes_verified)&&<p role="alert" className="notice error">A stored rule quotation does not match the current source. Re-extract and review this rule.</p>}
     <details><summary>Exact extracted quotation</summary><blockquote>{rule.extracted.source_quote}</blockquote></details>
    </article>)}
    {!linkedRules.length&&<p>{passage.disposition==='NON_RULE'?'Retained as policy context or source structure; no rule is linked to this passage.':'No current rule is linked to this passage. Its extraction or interpretation is still pending.'}</p>}
    {canReview&&linkedRules.length>0&&<button onClick={openRules}>Review / override rules for this policy</button>}
   </Panel>}
   {data.has_extraction&&<Panel title="Trace connected knowledge" sub="Published relationships only. Proposed rules remain visible in passage details. Each graph view shows at most six neighbors.">
    <div className="toolbar"><button onClick={overview}>Policy overview</button><button disabled={!back.length} onClick={()=>{graphRequest.current++;const previous=back[back.length-1];setGraph(previous.graph);setNext(previous.next);setGraphNode(null);setBack(history=>history.slice(0,-1))}}>Back</button><button disabled={!graphNode} onClick={()=>explore(graphNode.id)}>Explore selected node</button>{next&&<button onClick={()=>explore(next.focus,next.offset)}>Next six connections</button>}</div>
    {graph&&<Graph data={graph} onNode={setGraphNode} onExpand={node=>explore(node.id)}/>}<p>Rule corrections and approvals use the same current records as the Policy Rule Library.</p>
   </Panel>}
  </>}
 </>;
}
