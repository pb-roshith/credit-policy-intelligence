import React, {useEffect, useState} from 'react';
import {apiRequest} from '../../../api/client';
import {Panel} from '../components/ui';
import {api, post} from '../services/api';

const finished = ['Completed', 'Completed with errors', 'Failed'];

export default function PolicyUpload({policies, onRebuilt}) {
 const [policy, setPolicy] = useState('');
 const [stage, setStage] = useState(null);
 const [job, setJob] = useState(null);
 const [busy, setBusy] = useState(false);
 const [error, setError] = useState('');
 const jobId = job?.id;

 useEffect(() => {
  if (!jobId) return;
  let cancelled = false;
  let timer;
  async function poll() {
   try {
    const next = await apiRequest('/api/inventory/jobs/' + jobId);
    if (cancelled) return;
    setJob(next);
    if (finished.includes(next.status)) {
     await onRebuilt();
     return;
    }
   } catch (failure) {
    if (!cancelled) setError(failure.message);
   }
   if (!cancelled) timer = setTimeout(poll, 4000);
  }
  poll();
  return () => {cancelled = true; clearTimeout(timer);};
 }, [jobId, onRebuilt]);

 async function upload(event) {
  event.preventDefault();
  setBusy(true); setError(''); setStage(null); setJob(null);
  const body = new FormData(event.currentTarget);
  if (!policy) body.delete('policy_id');
  try {
   setStage(await api('/policy-uploads', {method:'POST', body}));
  } catch (failure) {setError(failure.message);}
  finally {setBusy(false);}
 }

 async function rebuild() {
  setBusy(true); setError('');
  try {
   const queued = await post('/policy-uploads/' + stage.upload_id + '/rebuild');
   setJob({id: queued.job_id, status: queued.status});
  } catch (failure) {setError(failure.message);}
  finally {setBusy(false);}
 }

 const running = job && !finished.includes(job.status);
 const snapshot = job?.report?.graph_rebuild;
 const ruleChanges = job?.report?.rule_changes;
 return <Panel title="Upload a policy or a new version">
  <form onSubmit={upload} className="toolbar">
   <label>Policy<select name="policy_id" value={policy} onChange={event=>setPolicy(event.target.value)}>
    <option value="">New policy</option>
    {policies.map(item=><option key={item.document_id} value={item.metadata.existing_policy_id}>{item.document_name}</option>)}
   </select></label>
   {!policy&&<>
    <label>Policy code<input name="code" maxLength={80} required/></label>
    <label>Policy title<input name="title" maxLength={200} required/></label>
   </>}
   <label>Version<input name="version" maxLength={24} required/></label>
   <label>Effective date<input name="effective_date" type="date" required/></label>
   <label>Policy file<input name="file" type="file" accept=".pdf,.docx,.txt,.text" required/></label>
   <button disabled={busy||running}>Upload and compare</button>
  </form>
  {error&&<p className="notice error" role="alert">{error}</p>}
  {stage&&<div>
   <p><strong>{stage.title} · Version {stage.version}</strong> · Effective {stage.effective_date}</p>
   {stage.previous_version&&stage.previous_source_available&&<p>Compared with version {stage.previous_version}. {stage.changes.added} added, {stage.changes.removed} removed, and {stage.changes.unchanged} unchanged passages.</p>}
   {stage.previous_version&&!stage.previous_source_available&&<p>Version {stage.previous_version} has no ingested passages for comparison.</p>}
   {[['Added passages',stage.changes.added_examples],['Removed passages',stage.changes.removed_examples]].map(([label, entries])=>entries.length>0&&
    <details key={label}><summary>{label} · up to 12 shown</summary>{entries.map((entry,index)=>
     <blockquote key={index}>{entry.clause_number&&<strong>Clause {entry.clause_number} </strong>}{entry.source_excerpt}</blockquote>)}</details>)}
   <button type="button" className="primary" onClick={rebuild} disabled={busy||!!job}>Revisit ontology and rebuild graph</button>
  </div>}
  {job&&<p role="status">{job.status}{snapshot&&` · ${snapshot.counts.nodes} nodes · ${snapshot.counts.relationships} relationships · ${snapshot.candidate_count} ontology gaps to review`}
   {!snapshot&&job.status==='Failed'&&' · Review the extraction job and retry unfinished work.'}</p>}
  {ruleChanges&&<details><summary>Published rule changes · {ruleChanges.added} added · {ruleChanges.removed} removed · {ruleChanges.unchanged} unchanged</summary>
   {[['Added',ruleChanges.added_examples],['Removed',ruleChanges.removed_examples]].map(([label,entries])=>
    entries.length>0&&<div key={label}><h4>{label}</h4>{entries.map(rule=><blockquote key={rule.id}><strong>{rule.name}</strong><p>{rule.quote}</p></blockquote>)}</div>)}
  </details>}
 </Panel>;
}
