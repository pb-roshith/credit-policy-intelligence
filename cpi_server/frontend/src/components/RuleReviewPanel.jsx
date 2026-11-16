import React,{useEffect,useState} from 'react';
import {apiRequest} from '../api/client';
import {formatPolicyCondition} from '../api/policyRepresentation';

export default function RuleReviewPanel({rule,canReview,onApproved}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [resolutions,setResolutions]=useState({}),[severity,setSeverity]=useState(rule.definition.severity||''),[source,setSource]=useState(rule.definition.data_source||''),[comment,setComment]=useState(''),[confirmed,setConfirmed]=useState(false);
 async function load(){const result=await apiRequest(`/api/policy-rules/${rule.id}/readiness`);setData(result);setResolutions(Object.fromEntries(result.dependencies.resolutions.map(r=>[r.dependency_id,{...r,conditions:JSON.stringify(r.conditions,null,2),exclusions:JSON.stringify(r.exclusions,null,2)}])))}
 useEffect(()=>{let active=true;setData(null);setError('');setSeverity(rule.definition.severity||'');setSource(rule.definition.data_source||'');setComment('');setConfirmed(false);apiRequest(`/api/policy-rules/${rule.id}/readiness`).then(result=>{if(!active)return;setData(result);setResolutions(Object.fromEntries(result.dependencies.resolutions.map(r=>[r.dependency_id,{...r,conditions:JSON.stringify(r.conditions,null,2),exclusions:JSON.stringify(r.exclusions,null,2)}])))}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[rule.id,rule.version,rule.status]);
 function update(id,key,value){setResolutions(current=>({...current,[id]:{...current[id],dependency_id:id,[key]:value}}))}
 const editable=canReview&&['Draft','Under Review','Approved','Active'].includes(rule.status);
 const complete=data?.dependencies.items.every(item=>{const r=resolutions[item.id];return r&&['covered','not_applicable'].includes(r.disposition)&&r.rationale?.trim().length>=3});
 async function approve(){setBusy(true);setError('');try{const items=data.dependencies.items.map(item=>{const r=resolutions[item.id];return {...r,conditions:JSON.parse(r.conditions||'null'),exclusions:JSON.parse(r.exclusions||'null')}});await apiRequest(`/api/policy-rules/${rule.id}/approve-reviewed`,{method:'POST',body:JSON.stringify({review_token:data.review_token,dependency_digest:data.dependencies.digest,resolutions:items,severity,data_source:source.trim(),comment:comment.trim(),confirmed})});await onApproved();await load();setConfirmed(false)}catch(e){setError(e instanceof SyntaxError?'Additional conditions must be valid structured data.':e.message)}finally{setBusy(false)}}
 return <section className="rule-knowledge-review" aria-label="Rule readiness and approval"><h3>Review this rule</h3>
 {error&&<p role="alert" className="data-message error">{error}</p>}
 {!data&&!error&&<p>Checking source and relevant dependencies...</p>}
 {data&&<>
 <p><strong>Applies when:</strong> {formatPolicyCondition(rule.definition.applicability_conditions)}</p>
 {rule.definition.applicability_exclusions&&<p><strong>Except when:</strong> {formatPolicyCondition(rule.definition.applicability_exclusions)}</p>}
 <ul>{data.checks.map(check=>{const ready=check.key==='data_source'?source.trim().length>=3:check.key==='severity'?!!severity:check.key==='dependencies'?complete:check.status==='pass';return <li key={check.key}>{ready?'✓':'○'} {check.message}</li>})}</ul>
 {!data.coverage.complete&&<p role="status">The policy still has {data.coverage.unresolved_spans} unresolved passages. This does not block this rule automatically. Its relevant dependencies below must be reviewed; the overall policy assessment remains incomplete.</p>}
 <h4>Relevant source dependencies ({data.dependencies.items.length})</h4>
 {!data.dependencies.items.length&&<p>No additional potential dependency sections were identified for this source-backed rule.</p>}
 {data.dependencies.items.map(item=>{const r=resolutions[item.id]||{};return <fieldset key={item.id}><legend>{item.label}</legend><p>{item.reason}</p><details><summary>Read source section{item.page?` — page ${item.page}`:''}</summary><blockquote style={{whiteSpace:'pre-wrap',maxHeight:320,overflow:'auto'}}>{item.source_excerpt}</blockquote></details><label>Effect on this rule<select disabled={!editable||busy} value={r.disposition||''} onChange={e=>update(item.id,'disposition',e.target.value)}><option value="">Choose after reading the source</option><option value="covered">Relevant conditions are represented</option><option value="not_applicable">Does not change this rule</option><option value="needs_work">Still needs interpretation or mapping</option></select></label><label>Source-backed rationale<textarea disabled={!editable||busy} value={r.rationale||''} onChange={e=>update(item.id,'rationale',e.target.value)} placeholder="Explain which conditions already cover this section, what guards are added, or why it does not affect this rule."/></label><details><summary>Additional applicability conditions or exceptions</summary><p>Add explicit guards when the source imposes conditions beyond those shown above. Missing request facts stay unknown; no values are assumed.</p><label>Additional conditions<textarea disabled={!editable||busy} value={r.conditions||'null'} onChange={e=>update(item.id,'conditions',e.target.value)}/></label><label>Additional exclusions<textarea disabled={!editable||busy} value={r.exclusions||'null'} onChange={e=>update(item.id,'exclusions',e.target.value)}/></label></details></fieldset>})}
 {editable&&<>
 <label>Actual input data source<input value={source} onChange={e=>setSource(e.target.value)} placeholder="Name the bank system or verified evidence supplying these inputs"/></label>
 <label>Outcome when the rule fails<select value={severity} onChange={e=>setSeverity(e.target.value)}><option value="">Choose severity</option><option value="BREACH">Breach</option><option value="WARNING">Warning</option></select></label>
 <label>Final review rationale<textarea value={comment} onChange={e=>setComment(e.target.value)}/></label>
 <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> I verified the rule and each relevant dependency. All applicable conditions, exceptions and overrides are represented or explicitly reviewed as not affecting this rule.</label>
 <button className="btn primary" disabled={busy||!data.structurally_current||!complete||!severity||source.trim().length<3||comment.trim().length<3||!confirmed} onClick={approve}>{busy?'Recording review...':['Approved','Active'].includes(rule.status)?'Review and re-approve rule':'Approve rule'}</button>
 </>}
 </>}
 </section>
}
