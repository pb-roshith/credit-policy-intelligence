import React,{useEffect,useRef,useState} from 'react';
import {api} from '../services/api';
import {Panel,Badge} from '../components/ui';
import Graph from './Graph';
import {graphNodeLabel,relationshipLabel} from './labels';

export default function SemanticGraphExplorer({policy='',focus='',inventory,onOpenRule}) {
 const [graph,setGraph]=useState(null),[history,setHistory]=useState([]),[error,setError]=useState(''),[loading,setLoading]=useState(false),[search,setSearch]=useState('');
 const request=useRef(0);
 async function load(focus='',offset=0,remember=true){
  const token=++request.current;setLoading(true);setError('');
  try{
   const result=await api('/semantic-graph?'+new URLSearchParams({focus,offset:String(offset),limit:'6'}));
   if(token!==request.current)return;
   if(remember&&graph)setHistory(h=>[...h,graph]);else if(!remember)setHistory([]);
   setGraph(result);setSearch('');
  }catch(e){if(token===request.current)setError(e.message)}
  finally{if(token===request.current)setLoading(false)}
 }
 useEffect(()=>{load(focus||(policy?'urn:cpi:policy:'+policy:''),0,false);return()=>{request.current++}},[policy,focus]);
 const focused=graph?.nodes.find(n=>n.id===graph.focus);
 const related=graph?.neighbors||[];
 const choices=related.filter(n=>[n.label,n.type,...n.relationships].join(' ').toLowerCase().includes(search.toLowerCase()));
 const isPolicy=focused?.type==='CreditPolicy';
 const policyRecord=isPolicy?inventory.policies.find(p=>'urn:cpi:policy:'+p.policy_id===focused.id):null;
 const publishedRules=related.filter(n=>n.type==='PolicyRule'&&n.relationships.includes('CONTAINS_RULE'));
 const currentRule=focused?.type==='PolicyRule'?inventory.rules.find(r=>r.id===focused.id):null;
 return <Panel title="Policy knowledge graph" sub="Click a policy to reveal its rules. Click a rule to follow its products, segments, metrics, thresholds, exceptions and approval requirements.">
  <div className="toolbar"><button onClick={()=>load('',0,false)}>All policies ({inventory.policies.length})</button><button disabled={!history.length||loading} onClick={()=>{request.current++;setLoading(false);setError('');setGraph(history.at(-1));setHistory(h=>h.slice(0,-1));setSearch('')}}>Back</button>{graph?.offset>0&&<button disabled={loading} onClick={()=>load(graph.focus,Math.max(0,graph.offset-6))}>Previous six</button>}{graph?.next_offset!=null&&<button disabled={loading} onClick={()=>load(graph.focus,graph.next_offset)}>Next six connections</button>}</div>
  {error&&<p role="alert" className="notice error">{error}</p>}
  {loading&&<p role="status">Loading connected knowledge…</p>}
  {focused&&<p><strong>{graphNodeLabel(focused)}</strong> · {isPolicy?`${publishedRules.length} published rules`:`${related.length} connected items`}{graph?.available_neighbors>6?' · Six connections shown at a time':''}</p>}
  {policyRecord&&<p>{policyRecord.rules} total extracted rules · {policyRecord.approved} published · {policyRecord.rules-policyRecord.approved} unpublished. Proposed or rejected extractions remain in the rule library.</p>}
  {currentRule&&<button onClick={()=>onOpenRule(currentRule)}>Open rule details and source</button>}
  {graph&&<Graph key={`${graph.focus}:${graph.offset}`} data={graph} onExpand={n=>load(n.id)} />}
  <div className="graph-directory">
   <h3>{!focused?'Browse all policies':isPolicy?'All published rules and policy connections':'All connections'}</h3>
   <p>{!focused?'Choose any policy below.':isPolicy?'Every published rule is available below; selecting one opens its connected details.':'Select a connected item to follow the relationship further.'}</p>
   <label>Search {isPolicy?'rules and connections':!focused?'policies':'connections'}<input value={search} onChange={e=>setSearch(e.target.value)}/></label>
   {!focused?<div className="graph-directory-list">{inventory.policies.filter(p=>p.title.toLowerCase().includes(search.toLowerCase())).map(p=><button key={p.policy_id} disabled={loading} onClick={()=>load('urn:cpi:policy:'+p.policy_id)}><strong>{p.title}</strong><small>{p.approved} published rules · {p.rules} extracted</small></button>)}</div>:
    <div className="graph-directory-list">{choices.map(n=><button key={n.id} disabled={loading} onClick={()=>load(n.id)}><Badge>{n.type}</Badge><strong>{graphNodeLabel(n)}</strong><small>{n.relationships.map(relationshipLabel).join(' · ')}</small></button>)}</div>}
   {focused&&!choices.length&&<p>{related.length?'No connections match your search.':'No further connections are recorded for this item.'}</p>}
  </div>
 </Panel>;
}
