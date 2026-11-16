import React,{useMemo,useState,useRef} from 'react';
import {Plus,Minus,Maximize,MousePointer2,Network} from 'lucide-react';
import {Badge,Source,Empty} from '../components/ui';
import {graphNodeLabel,relationshipLabel,wrapGraphLabel} from './labels';
const colors={CreditPolicy:'#446e99',PolicyVersion:'#6497be',Product:'#457bad',CustomerSegment:'#bc8b30',RiskMetric:'#8b7ac1',Threshold:'#d88135',ConditionGroup:'#b89354',SourcePassage:'#81949c',TaxonomyConcept:'#4c9c90',PolicyRule:'#288879',Condition:'#e0a04b',Outcome:'#8b7ac1',ApprovalAuthority:'#8b7ac1',PolicyClause:'#6497be',PolicyDocument:'#446e99',PolicySection:'#94b3c9',Exception:'#d77963',DOMAIN:'#245b54',ENTITY:'#388c7d',ATTRIBUTE:'#6aa9a0'};
export default function Graph({data,onNode,onExpand,onDocument,trace=false}) {
 const [selected,setSelected]=useState(null),[zoom,setZoom]=useState(1),[pan,setPan]=useState({x:0,y:0}),[positions,setPositions]=useState({}),[hover,setHover]=useState(null);
 const drag=useRef(null),svg=useRef(null);
 const {nodes=[],edges=[]}=data||{};
 const layout=useMemo(()=>{
   const output={};
   if(data?.focus&&nodes.some(n=>n.id===data.focus)){
    output[data.focus]={x:450,y:280};
    const neighbors=nodes.filter(n=>n.id!==data.focus);
    neighbors.forEach((n,i)=>{const angle=i/Math.max(1,neighbors.length)*Math.PI*2-Math.PI/2;output[n.id]={x:450+Math.cos(angle)*290,y:280+Math.sin(angle)*195}});
    return output;
   }
   if(trace){nodes.forEach((n,i)=>output[n.id]={x:85+i*(730/Math.max(nodes.length-1,1)),y:210+(i%2)*80});return output}
   const types=[...new Set(nodes.map(n=>n.type))];
   if(types.length===1&&nodes.length<=8){nodes.forEach((n,i)=>{const a=i/nodes.length*Math.PI*2-Math.PI/2;output[n.id]={x:450+(nodes.length===1?0:Math.cos(a)*220),y:285+(nodes.length===1?0:Math.sin(a)*170)}});return output}
   types.forEach((type,ti)=>{const group=nodes.filter(n=>n.type===type);const angle=ti/types.length*Math.PI*2-Math.PI/2;const cx=450+Math.cos(angle)*255,cy=285+Math.sin(angle)*175;
    group.forEach((n,i)=>{const a=i/group.length*Math.PI*2;const radius=group.length===1?0:Math.min(110,28+group.length*8);output[n.id]={x:cx+Math.cos(a)*radius,y:cy+Math.sin(a)*radius}})});
   return output;
 },[nodes,trace,data?.focus]);
 const point=id=>positions[id]||layout[id]||{x:450,y:285};
 const chosen=nodes.find(n=>n.id===selected);
 function start(e,id){e.stopPropagation();const rect=svg.current.getBoundingClientRect();drag.current={id,startX:e.clientX,startY:e.clientY,origin:id?point(id):pan,scale:900/rect.width/zoom};e.currentTarget.setPointerCapture(e.pointerId)}
 function move(e){if(!drag.current)return;const d=drag.current,dx=(e.clientX-d.startX)*d.scale,dy=(e.clientY-d.startY)*d.scale;if(d.id)setPositions(p=>({...p,[d.id]:{x:d.origin.x+dx,y:d.origin.y+dy}}));else setPan({x:d.origin.x+dx,y:d.origin.y+dy})}
 function end(){drag.current=null}
 function activate(n){setSelected(n.id);onNode?.(n);onExpand?.(n)}
 if(!nodes.length)return <Empty>No connected knowledge is available in this selection. Extract a policy or choose another selection.</Empty>;
 return <div className="graph-container"><div className="graph-canvas"><div className="graph-status"><span className="live-dot"/>{nodes.length} nodes · {edges.length} relationships</div><div className="graph-tools"><button aria-label="Zoom in" onClick={()=>setZoom(z=>Math.min(z+.2,2.5))}><Plus size={16}/></button><button aria-label="Zoom out" onClick={()=>setZoom(z=>Math.max(z-.2,.4))}><Minus size={16}/></button><button aria-label="Reset graph" onClick={()=>{setZoom(1);setPan({x:0,y:0});setPositions({})}}><Maximize size={16}/></button></div><svg ref={svg} viewBox="0 0 900 570" role="img" aria-label="Interactive policy relationship graph" onPointerDown={e=>start(e,null)} onPointerMove={move} onPointerUp={end} onPointerCancel={end}>
 <defs><pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="#d7dfdc"/></pattern><marker id="arrow" viewBox="0 0 10 10" refX="24" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#aebdb6"/></marker></defs><rect width="900" height="570" fill="url(#dots)"/>
 <g transform={`translate(${450+pan.x},${285+pan.y}) scale(${zoom}) translate(-450,-285)`}>{edges.map(e=>{const a=point(e.source),b=point(e.target),active=selected===e.source||selected===e.target||hover===e.id;return <g key={e.id} onMouseEnter={()=>setHover(e.id)} onMouseLeave={()=>setHover(null)}><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={active?'#307e70':'#bacbc4'} strokeWidth={active?2.2:1.2} opacity={selected&&!active ? .28 : .8} markerEnd="url(#arrow)"/>{(active||trace||nodes.length<=8)&&<text className="edge-label" x={(a.x+b.x)/2} y={(a.y+b.y)/2-8} textAnchor="middle">{relationshipLabel(e.predicate)}</text>}</g>})}
 {nodes.map(n=>{const p=point(n.id),active=selected===n.id;return <g key={n.id} role="button" aria-label={graphNodeLabel(n)+(onExpand?' - open connections':'')} tabIndex="0" transform={`translate(${p.x},${p.y})`} onPointerDown={e=>start(e,n.id)} onClick={e=>{e.stopPropagation();activate(n)}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate(n)}}} className="graph-node"><circle r={active?23:n.type==='PolicyRule'?20:15} fill="white" stroke={colors[n.type]||'#669989'} strokeWidth={active?4:2.5}/><circle r={n.type==='PolicyRule'?8:5} fill={colors[n.type]||'#669989'}/><text y={38} textAnchor="middle" className="node-label">{wrapGraphLabel(graphNodeLabel(n)).map((line,i)=><tspan key={i} x={0} dy={i?14:0}>{line}</tspan>)}</text><title>{graphNodeLabel(n)+' - '+n.type+' - '+(n.neighbor_count||0)+' connections'}</title></g>})}</g></svg><div className="graph-help"><MousePointer2 size={13}/> Drag to arrange - {onExpand?'Click a node to open its connections':'Click for evidence'}</div><div className="graph-legend">{[...new Set(nodes.map(n=>n.type))].slice(0,8).map(t=><span key={t}><i style={{background:colors[t]||'#669989'}}/>{t.replace(/([a-z])([A-Z])/g,'$1 $2')}</span>)}</div></div>
 {chosen&&<aside className="graph-inspector"><div className="eyebrow">Selected {chosen.type}</div><h3>{graphNodeLabel(chosen)}</h3><Badge>{chosen.status}</Badge>{chosen.payload&&<p className="inspector-text">{typeof chosen.payload === 'object' ? JSON.stringify(chosen.payload,null,2) : chosen.payload}</p>}<Source source={chosen.provenance} onDocument={onDocument}/><h3>Connected relationships</h3>{edges.filter(e=>e.source===chosen.id||e.target===chosen.id).map(e=><div className="edge-detail" key={e.id}><strong>{relationshipLabel(e.predicate)}</strong><small>{nodes.find(n=>n.id===(e.source===chosen.id?e.target:e.source))?.label}</small><details><summary>Edge provenance</summary><Source source={e.provenance}/></details></div>)}</aside>}</div>
}
