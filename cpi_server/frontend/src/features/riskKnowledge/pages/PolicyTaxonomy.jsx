import React,{useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import {Panel,Badge,Source,Empty} from '../components/ui';

export default function PolicyTaxonomy({showSource}) {
 const [data,setData]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const [policy,setPolicy]=useState(''),[query,setQuery]=useState(''),[view,setView]=useState('tree'),[selected,setSelected]=useState(null),[limit,setLimit]=useState(40);
 async function reload(){setLoading(true);setError('');try{setData(await api('/policy-taxonomy'));setSelected(null)}catch(e){setError(e.message)}finally{setLoading(false)}}
 useEffect(()=>{let active=true;api('/policy-taxonomy').then(d=>{if(active)setData(d)}).catch(e=>{if(active)setError(e.message)}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[]);
 const coverage=useMemo(()=>(data?.coverage||[]).filter(c=>!policy||String(c.policy_id)===policy),[data,policy]);
 const clauseIds=useMemo(()=>new Set(coverage.map(c=>c.clause_id)),[coverage]);
 const assignments=useMemo(()=>(data?.assignments||[]).filter(a=>clauseIds.has(a.clause_id)),[data,clauseIds]);
 const nodes=useMemo(()=>{
  const children=new Map();for(const n of data?.tree||[]){const count=n.clause_ids.filter(c=>clauseIds.has(c)).length;if(!count)continue;const group=children.get(n.parent_id)||[];group.push({...n,count});children.set(n.parent_id,group)}
  const result=[];function walk(parent){for(const n of (children.get(parent)||[]).sort((a,b)=>a.label.localeCompare(b.label))){result.push(n);walk(n.node_id)}}walk(null);return result;
 },[data,clauseIds]);
 const selectedNode=data?.tree.find(n=>n.node_id===selected);
 const selectedConcept=data?.dictionary.find(c=>c.concept_id===selected);
 const evidence=useMemo(()=>{
  let rows=view==='unclassified'?coverage.filter(c=>c.disposition==='UNCLASSIFIED'):view==='structure'?coverage.filter(c=>c.disposition==='STRUCTURE'):assignments;
  if(selectedNode)rows=rows.filter(a=>selectedNode.path.every((p,i)=>a.path?.[i]===p));
  if(selectedConcept)rows=rows.filter(a=>a.category_id===selected||a.topic_id===selected);
  const seen=new Set();return rows.filter(a=>{if(seen.has(a.clause_id))return false;seen.add(a.clause_id);return !query||[a.source.document_name,a.source.passage,a.category,a.topic].join(' ').toLowerCase().includes(query.toLowerCase())});
 },[assignments,coverage,view,selected,selectedNode,selectedConcept,query]);
 function exportJSON(){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='policy-taxonomy.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 function changeView(value){setView(value);setSelected(null);setLimit(40)}
 if(loading)return <p role="status">Reading current policy sources and building the classification tree…</p>;
 if(error)return <div role="alert" className="notice error">{error}<button onClick={reload}>Retry</button></div>;
 if(!data)return <Empty>No policy taxonomy is available.</Empty>;
 const counts=value=>coverage.filter(c=>c.disposition===value).length;
 return <>
  <Panel title="Policy classification taxonomy" sub="A controlled dictionary and observed hierarchy, grounded in current policy passages." action={<Badge>PROPOSED</Badge>}>
   <p>Assignments are proposals for review. Product, segment and geography values show explicit mentions in a passage. They do not establish policy applicability.</p>
   <div className="toolbar"><label>Policy<select aria-label="Filter taxonomy by policy" value={policy} onChange={e=>{setPolicy(e.target.value);setSelected(null);setLimit(40)}}><option value="">All policies</option>{data.documents.map(d=><option key={d.policy_id} value={d.policy_id}>{d.title}</option>)}</select></label><label>Search evidence<input aria-label="Search policy taxonomy" value={query} onChange={e=>{setQuery(e.target.value);setLimit(40)}}/></label><div className="button-row"><button onClick={reload}>Refresh from source</button><button onClick={exportJSON}>Export policy taxonomy JSON</button></div></div>
   <div className="knowledge-counts"><span><b>{coverage.length}</b> stored passages</span><span><b>{counts('CLASSIFIED')}</b> classified</span><span><b>{counts('STRUCTURE')}</b> structural</span><span><b>{counts('UNCLASSIFIED')}</b> unclassified</span><span><b>{data.summary.missing_source_policies}</b> policies with missing/stale source</span></div>
   <div className="tabs" role="tablist" aria-label="Policy taxonomy outputs">{[['tree','Classification tree'],['dictionary','Dictionary'],['dimensions','Dimensions'],['unclassified','Unclassified'],['structure','Source structure']].map(([key,label])=><button role="tab" aria-selected={view===key} className={view===key?'active':''} key={key} onClick={()=>changeView(key)}>{label}</button>)}</div>
  </Panel>
  {view==='tree'&&<Panel title="Observed classification tree" sub="Domain → policy area → product → category → topic. Counts show distinct supporting passages."><p>Unspecified values remain explicit. Multiple areas or products are retained together without inventing individual rule relationships.</p><div className="policy-taxonomy-tree" role="tree" aria-label="Observed policy classification">{nodes.map(n=><button key={n.node_id} role="treeitem" aria-level={n.level+1} aria-selected={selected===n.node_id} className={'tree-row '+(selected===n.node_id?'active':'')} style={{paddingLeft:16+n.level*22}} onClick={()=>{setSelected(n.node_id);setLimit(40)}}><span>{n.label}</span><small>{n.count}</small></button>)}</div>{!nodes.length&&<Empty>No observed classification branches for this selection.</Empty>}</Panel>}
  {view==='dictionary'&&<Panel title="Controlled classification dictionary" sub="Vocabulary definitions are curated; supporting occurrences come from policy content."><div className="policy-taxonomy-table"><table><thead><tr><th>Concept</th><th>Definition / inclusion</th><th>Kind</th><th>Support in selection</th></tr></thead><tbody>{data.dictionary.map(c=><tr key={c.concept_id}><td><button className="text-button" onClick={()=>{setSelected(c.concept_id);setLimit(40)}}>{c.preferred_name}</button><small>{c.concept_id}</small></td><td>{c.definition}<details><summary>Aliases and criteria</summary><p>{c.inclusion_criteria}</p><p>{c.exclusion_criteria}</p><p>Workbook references: {c.schema_references.map(s=>s.source_entity+' / '+s.preferred_name).join('; ')||'No exact-label references'}. References require separate binding review.</p></details></td><td>{c.kind}</td><td>{c.supporting_clause_ids.filter(id=>clauseIds.has(id)).length}<br/><Badge>{c.review_status}</Badge>{!c.support_count&&<small>Not observed in source</small>}</td></tr>)}</tbody></table></div></Panel>}
  {view==='dimensions'&&<Panel title="Observed classification dimensions" sub="Values need literal evidence. Unmentioned values are not filled in.">{['policy_area','product','customer_segment','geography'].map(dimension=><section key={dimension}><h3>{dimension.replaceAll('_',' ')}</h3>{data.facets.filter(f=>f.dimension===dimension&&f.evidence.some(e=>clauseIds.has(e.source.clause_id))).map(f=><details key={f.value}><summary>{f.value} · {f.evidence.filter(e=>clauseIds.has(e.source.clause_id)).length} supporting passages</summary>{f.evidence.filter(e=>clauseIds.has(e.source.clause_id)).slice(0,10).map(e=><Source key={e.source.clause_id} source={e.source} onDocument={showSource}/>)}</details>)}{!data.facets.some(f=>f.dimension===dimension&&f.evidence.some(e=>clauseIds.has(e.source.clause_id)))&&<p>No explicit values observed.</p>}</section>)}</Panel>}
  {view!=='dimensions'&&<Panel title={view==='unclassified'?'Unclassified source passages':view==='structure'?'Structural source passages':selectedNode?selectedNode.path.join(' → '):selectedConcept?selectedConcept.preferred_name+' — supporting evidence':'Supporting source passages'} sub={evidence.length+' distinct passages; complete text and source version retained.'}>
   {selected&&<button onClick={()=>setSelected(null)}>Show all evidence</button>}
   {evidence.slice(0,limit).map(a=><article key={a.clause_id}>{a.path&&<p>{a.path.join(' → ')}</p>}{a.reason&&<p>{a.reason}</p>}<p><Badge>SOURCE</Badge> · {a.clause_id} · <Badge>{a.content_role}</Badge>{a.path&&<> · <Badge>{a.status}</Badge></>}</p><Source source={a.source} onDocument={showSource}/></article>)}
   {!evidence.length&&<Empty>No supporting passages in this selection.</Empty>}{evidence.length>limit&&<button onClick={()=>setLimit(n=>n+40)}>Show 40 more passages</button>}
  </Panel>}
  <Panel title="Method and coverage limits"><ul>{data.methodology.map(m=><li key={m}>{m}</li>)}</ul><small>Vocabulary: {data.version} · source digest: {data.source_digest}</small></Panel>
 </>;
}
