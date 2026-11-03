import React from 'react';
import {ArrowUpRight, Check, X, FileText, ExternalLink, CircleHelp} from 'lucide-react';
import {post,exportUrl} from '../services/api';
export const ReviewerContext=React.createContext('Current CPI session');

export const pretty=s=>String(s??'Unknown').replaceAll('_',' ').toLowerCase().replace(/\b\w/g,c=>c.toUpperCase());
export function Badge({children,tone=''}) {return <span className={'badge '+(tone||String(children).toLowerCase())}>{pretty(children)}</span>}
export function Panel({title,sub,action,children,className=''}) {return <section className={'panel '+className}>{title&&<div className="panel-head"><div><h2>{title}</h2>{sub&&<p>{sub}</p>}</div>{action}</div>}{children}</section>}
export function Empty({children}) {return <div className="empty"><CircleHelp size={26}/><p>{children}</p></div>}
export function Source({source,onDocument}) {
 if(!source)return null;
 return <div className="source-block"><div className="eyebrow"><FileText size={13}/> Source evidence</div><strong>{source.document_name}</strong><div className="source-meta">{[source.section,source.sheet,source.cell,source.page?'Page '+source.page:null,source.clause?'Clause '+source.clause:null].filter(Boolean).join(' · ')}</div><blockquote>{source.passage}</blockquote><div className="source-meta">Version {source.version||'UNKNOWN'} · Effective {source.effective_date||'UNKNOWN'} · {source.origin}</div>{onDocument&&<button className="text-button" onClick={()=>onDocument(source.document_id)}>View source document <ArrowUpRight size={14}/></button>}</div>
}
export function Quality({validation}) {return <div className="quality">{Object.entries(validation||{}).map(([k,v])=><div key={k} className={v?'pass':'fail'}>{v?<Check size={14}/>:<X size={14}/>}<span>{pretty(k)}</span></div>)}</div>}
export function Modal({title,onClose,children,wide=false}) {return <div className="modal-shade" onClick={onClose}><section role="dialog" aria-modal="true" aria-label={title} className={'modal '+(wide?'wide':'')} onClick={e=>e.stopPropagation()}><header><h2>{title}</h2><button aria-label="Close dialog" className="icon-button" onClick={onClose}><X size={20}/></button></header><div className="modal-content">{children}</div></section></div>}
export function ReviewControls({kind,id,run,onRefresh}) {
 const reviewer=React.useContext(ReviewerContext),[notes,setNotes]=React.useState('');
 async function submit(status){if(notes.trim().length<3)throw new Error('Add a short review note before recording your decision.');await post(`/review/${kind}/${id}`,{status,reviewer,notes});await onRefresh()}
 return <div className="review-controls"><label>Signed-in reviewer<input value={reviewer} readOnly/></label><label>Review notes<textarea placeholder="Record the evidence for your decision…" value={notes} onChange={e=>setNotes(e.target.value)}/></label><div className="button-row"><button className="primary" onClick={()=>run(()=>submit('APPROVED'),'Approval recorded')}><Check size={15}/>Approve</button><button onClick={()=>run(()=>submit('REVIEWED'),'Marked reviewed')}>Mark reviewed</button><button className="danger-button" onClick={()=>run(()=>submit('REJECTED'),'Rejection recorded')}>Reject</button></div></div>
}
export function Conditions({rule}) {
 const print=g=><div className="condition-group"><span className="logic">{g.logic}</span>{g.conditions.map((c,i)=><div className="condition" key={i}><span>{c.normalized_term||c.original_term}</span><b>{c.operator}</b><code>{JSON.stringify(c.value)}</code><small>{c.unit}</small></div>)}{g.groups?.map((sub,i)=><React.Fragment key={i}>{print(sub)}</React.Fragment>)}</div>;
 return <><h3>Scope</h3>{rule.scope.length?rule.scope.map((c,i)=><div className="condition" key={i}><span>{c.normalized_term||c.original_term}</span><b>{c.operator}</b><code>{String(c.value)}</code></div>):<p className="muted">No explicit scope restriction.</p>}<h3>Conditions</h3>{print(rule.conditions)}<h3>Outcome</h3><div className="outcome"><strong>{rule.outcome.action}</strong><span>{rule.outcome.authority||rule.outcome.value||'UNKNOWN'}</span></div>{rule.exceptions.length>0&&<><h3>Explicit exceptions</h3>{rule.exceptions.map((e,i)=><React.Fragment key={i}>{print(e)}</React.Fragment>)}</>}</>
}
export function ExportButton({kind}) {return <a className="button" href={exportUrl(kind)} target="_blank" rel="noreferrer">Export JSON <ExternalLink size={14}/></a>}
