import {assessmentText} from '../api/displayText';
import React,{useState} from 'react';
import {ChevronDown,MessageSquareText,ListFilter} from 'lucide-react';
import {Badge} from './ui';

export default function GraphAssessmentTrace({review,onEvidence}) {
 const [status,setStatus]=useState('Unable to Determine'),[query,setQuery]=useState(''),[limit,setLimit]=useState(20);
 const report=review.applicability_report,explanation=review.graph_rag_explanation;
 const rules=report.decisions.filter(d=>d.candidate_type==='Rule'&&(!status||d.applicability===status)&&(!query||[d.rule_name,d.policy_name].join(' ').toLowerCase().includes(query.toLowerCase())));
 const statistics=[
  {label:'Published rules checked',value:report.graph_rule_count,tone:'checked'},
  {label:'Matched',value:report.applicable_rule_count,tone:'matched'},
  {label:'Excluded',value:report.excluded_rule_count,tone:'excluded'},
  {label:'Needs information',value:report.unresolved_rule_count,tone:'unresolved',note:'Scope or request facts'},
 ];
 return <details className="card graph-matching-card graph-matching-collapsible">
  <summary className="card-head graph-matching-toggle"><div><h2>Knowledge graph matching</h2><p>Request facts select rules through graph relationships. AI explains the retrieved evidence.</p></div><ChevronDown className="graph-matching-outer-chevron" size={20} aria-hidden="true"/></summary>
  <div className="graph-matching-content">
   <div className="graph-matching-stats" role="list" aria-label="Graph matching counts">{statistics.map(stat=><div className={'graph-matching-stat '+stat.tone} role="listitem" key={stat.tone}><strong>{Number(stat.value||0).toLocaleString()}</strong><span>{stat.label}</span>{stat.note&&<small>{stat.note}</small>}</div>)}</div>
   <div className="graph-matching-status"><div><span>Overall status</span><Badge>{review.compliance_status}</Badge></div><p>Proposed extractions and unresolved policy passages keep coverage incomplete.</p></div>
   <div className="graph-matching-sections">
    {explanation&&<details className="graph-matching-disclosure"><summary><span><MessageSquareText size={17}/>AI explanation of graph results</span><ChevronDown className="graph-matching-chevron" size={17}/></summary><div className="graph-matching-detail">
     <p>{assessmentText(explanation.summary)}</p>{explanation.notice&&<p className="graph-matching-note">{assessmentText(explanation.notice)}</p>}
     <p className="graph-matching-note">{explanation.source} - Explanation only; graph decisions and assessment results remain authoritative.</p>
     <div className="graph-matching-explanations">{explanation.rules.map(r=><div key={r.rule_id}><strong>{review.findings.find(f=>f.rule_id===r.rule_id)?.rule_name}</strong><p>{assessmentText(r.explanation)}</p></div>)}</div>
     {!!explanation.omitted_rules&&<p className="graph-matching-note">{explanation.omitted_rules} additional matching rules are listed in the findings table.</p>}
    </div></details>}
    <details className="graph-matching-disclosure"><summary><span><ListFilter size={17}/>Inspect matched, excluded and unresolved rules</span><ChevronDown className="graph-matching-chevron" size={17}/></summary><div className="graph-matching-detail">
     <div className="assessment-filters graph-matching-filters"><label>Matching result<select value={status} onChange={e=>{setStatus(e.target.value);setLimit(20)}}><option value="">All rules</option><option>Applicable</option><option>Not Applicable</option><option>Unable to Determine</option></select></label><label>Search policy or rule<input value={query} placeholder="Search policies or rules" onChange={e=>{setQuery(e.target.value);setLimit(20)}}/></label></div>
     <p className="graph-matching-note">{rules.length} matching decisions</p>
     <div className="graph-matching-decisions">{rules.slice(0,limit).map(d=><details className="graph-matching-rule" key={d.candidate_id}><summary><span><strong>{d.rule_name}</strong><small>{d.policy_name}</small></span><Badge>{d.applicability}</Badge></summary><div className="graph-matching-rule-detail">
      <p>{d.reason}</p>{d.missing_information.length>0&&<p>Missing: {d.missing_information.join(', ')}</p>}
      <button type="button" className="btn secondary" onClick={()=>onEvidence({policy_id:d.policy_id,clause_id:d.source_clause_id,matching_trace:d})}>Open policy evidence</button>
      <p className="graph-matching-path">Graph path: <code>{d.graph_path.join(' > ')}</code></p>
      {d.trace.map((t,i)=><p key={i}><strong>{t.predicate.replaceAll('_',' ').toLowerCase()}</strong>: {t.outcome||'Source-backed policy scope'}{t.expected?' - Required '+JSON.stringify(t.expected):''}{t.fact?' - Request fact '+JSON.stringify(t.fact.value??'Missing or conflicting'):''}</p>)}
     </div></details>)}</div>
     {rules.length>limit&&<button type="button" className="btn secondary graph-matching-more" onClick={()=>setLimit(n=>n+20)}>Show 20 more decisions</button>}
    </div></details>
   </div>
  </div>
 </details>;
}
