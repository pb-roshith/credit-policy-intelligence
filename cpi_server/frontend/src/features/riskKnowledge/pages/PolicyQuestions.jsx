import React, {useState} from 'react';
import {Badge, Panel} from '../components/ui';
import {api} from '../services/api';

const questions = [
 ['borrower','Which policies apply to this borrower?'],
 ['industry','Which policies cover this industry, subsector, or industry tier?'],
 ['geography','Which policies specify this country or jurisdiction?'],
 ['product','Which rules specify this product?'],
 ['rating','Which rules depend on credit rating?'],
 ['exposure','What exposure limits are documented?'],
 ['collateral','What collateral requirements are documented?'],
 ['breach_approval','What approval is required if a threshold is exceeded?'],
 ['exceptions','What exception provisions are documented?'],
 ['policy_class','Which policy class is linked to this rule?'],
 ['effective','Which rule edition was effective on a date?'],
 ['relationship','Browse a relationship type'],
 ['coverage','Which ontology or source gaps need review?'],
];
const valueLabels = {industry:'Industry, subsector or tier', geography:'Country or jurisdiction', product:'Product', policy_class:'Rule ID'};

function conditionText(group) {
 const parts = [...group.conditions.map(item=>[item.field, item.operator,
  Array.isArray(item.value)?item.value.join(', '):String(item.value ?? ''), item.unit].filter(Boolean).join(' ')),
  ...group.groups.map(child=>'('+conditionText(child)+')')];
 return group.logic==='NOT'?'NOT ('+parts.join(' ')+')':parts.join(' '+group.logic+' ');
}

export default function PolicyQuestions({policies, relationships=[], onFocus}) {
 const [question, setQuestion] = useState('borrower');
 const [policy, setPolicy] = useState('');
 const [value, setValue] = useState('');
 const [date, setDate] = useState('');
 const [request, setRequest] = useState('');
 const [result, setResult] = useState(null);
 const [parameters, setParameters] = useState(null);
 const [error, setError] = useState('');
 const [busy, setBusy] = useState(false);
 const showRequest = question === 'borrower' || ['exposure','collateral','breach_approval','exceptions','rating'].includes(question);

 async function fetchAnswers(input, offset = 0) {
  setError(''); setBusy(true);
  try {
   const data = await api('/semantic-questions?' + new URLSearchParams({...input, offset}));
   setResult(previous=>offset ? {...data, results:[...previous.results, ...data.results]} : data);
   setParameters(input);
  } catch (failure) {setError(failure.message);}
  finally {setBusy(false);}
 }

 function submit(event) {
  event.preventDefault();
  setResult(null);
  const input = {question};
  if (policy && !['coverage','relationship'].includes(question)) input.policy_id = policy;
  if (value && (valueLabels[question] || ['effective','relationship'].includes(question))) input.value = value.trim();
  if (date && question === 'effective') input.on_date = date;
  if (showRequest && request) input.request_id = request.trim();
  fetchAnswers(input);
 }

 return <Panel title="Ask the policy graph">
  <form onSubmit={submit} className="toolbar">
   <label>Question<select value={question} disabled={busy} onChange={event=>{setQuestion(event.target.value);setValue('');setResult(null);setError('');}}>
    {questions.map(([id,label])=><option key={id} value={id}>{label}</option>)}
   </select></label>
   {!['coverage','relationship'].includes(question)&&<label>Policy<select value={policy} required={question==='effective'} onChange={event=>setPolicy(event.target.value)}>
    <option value="">{question==='effective'?'Select a policy':'All policies'}</option>
    {policies.map(item=><option key={item.policy_id} value={item.policy_id}>{item.title}</option>)}
   </select></label>}
   {(valueLabels[question]||question==='effective')&&
    <label>{valueLabels[question]||'Rule ID (optional)'}<input maxLength={240} value={value} required={!!valueLabels[question]} onChange={event=>setValue(event.target.value)}/></label>}
   {question==='relationship'&&<label>Relationship<select value={value} required onChange={event=>setValue(event.target.value)}>
    <option value="">Select a relationship</option>{relationships.map(rel=><option value={rel.predicate} key={rel.predicate}>{rel.label}</option>)}
   </select></label>}
   {question==='effective'&&<label>Effective on<input type="date" value={date} onChange={event=>setDate(event.target.value)} required/></label>}
   {showRequest&&<label>Credit request ID{question!=='borrower'?' (optional)':''}<input maxLength={120} value={request} onChange={event=>setRequest(event.target.value)} required={question==='borrower'}/></label>}
   <button disabled={busy} className="primary">{busy?'Checking graph…':'Find answers'}</button>
  </form>
  {error&&<p role="alert" className="notice error">{error}</p>}
  {result?.relationship_candidates&&<>
   <p>{result.policies} policies · {result.source_passages} passages · {result.published_rules} published rules · {result.scope_needs_review.length} policy scopes need review</p>
   {result.source_relationship_candidates?.length>0&&<ul>
    {result.source_relationship_candidates.map(item=><li key={item.label}><details>
     <summary>{item.label} · {item.count} source passages to review</summary>
     <p>{item.policy} · Version {item.version} · Source ID {item.clause_id}</p><blockquote>{item.quote}</blockquote>
    </details></li>)}
   </ul>}
   <ul>{result.relationship_candidates.map(item=><li key={item.field}><details>
    <summary>{item.field} · {item.count} comparisons without a typed field binding</summary>
    <p>{item.policy} · Version {item.version} · Source ID {item.clause_id}</p><blockquote>{item.quote}</blockquote>
   </details></li>)}</ul>
  </>}
  {result?.results&&<>
   {result.selected_version&&<p>Version {result.selected_version.version} · Effective from {result.selected_version.effective_date}</p>}
   {result.reason&&<p>{result.reason}</p>}
   {!result.total&&!result.reason&&<p>No published graph path supports an answer for those inputs.</p>}
   {result.total>0&&<p role="status">{result.total} {result.question==='borrower'?'policy decisions':'source-backed results'}{result.match_basis==='published_source_paths'?' · Other conditions may still affect applicability.':''}</p>}
   {result.results.map((row,index)=><details key={row.id+':'+(row.relationship||index)} className="asset-row">
    <summary><strong>{row.label||row.policy_name}</strong> {row.version&&` · Version ${row.version}`} {row.applicability&&<Badge>{row.applicability}</Badge>}</summary>
    {row.policy&&<p>{row.policy} · {row.id}{row.synthetic?' · Synthetic source':''}</p>}
    {row.scope&&<p>{row.scope_type} · {row.scope}{row.inherited_scope?' · Inherited policy scope':''}</p>}
    {row.reason&&<p>{row.reason}</p>}
    {row.conditions&&<p>Conditions · {conditionText(row.conditions)}</p>}
    {row.thresholds?.map((boundary,i)=><p key={i}>{boundary.metric_key} {boundary.operator} {boundary.value} {boundary.unit}</p>)}
    {row.approvals?.map((approval,i)=><p key={i}>{approval.triggered_by_breach?'Breach trigger · ':approval.above_threshold?'Above-threshold trigger · ':''}{approval.requirement.decision_type} · {approval.authorities.join(', ')}{approval.requirement.notes&&` · ${approval.requirement.notes}`}</p>)}
    {result.question==='policy_class'&&<p>{row.derived_from_classes.length?`Derived from ${row.derived_from_classes.join(', ')}`:'Explicit class derivation is unavailable.'} {row.policy_classes.length>0&&`Taxonomy classifications are ${row.policy_classes.join(', ')}.`}</p>}
    {row.exception_ids?.length>0&&<p>Linked exceptions {row.exception_ids.join(', ')}</p>}
    {row.source_quote&&<blockquote>{row.source_quote}</blockquote>}
    {(row.scope_sources||row.sources)?.map(source=><details key={source.node_id}><summary>Source passage{source.clause? ' · Clause '+source.clause:''}{source.page?' · Page '+source.page:''}</summary><blockquote>{source.quote}</blockquote></details>)}
    {result.question!=='effective'&&<button type="button" onClick={()=>onFocus(row.graph_node_id||row.id)}>Open in graph</button>}
   </details>)}
   {result.next_offset!=null&&<button disabled={busy} onClick={()=>fetchAnswers(parameters,result.next_offset)}>Show more results</button>}
  </>}
 </Panel>;
}
