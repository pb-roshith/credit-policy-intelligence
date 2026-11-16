import React,{useState} from 'react';
import {Panel,Source} from '../components/ui';
import PolicyTaxonomy from './PolicyTaxonomy';
export default function Taxonomy(props) {
 const [layer,setLayer]=useState('policy'),[query,setQuery]=useState(''),[selected,setSelected]=useState(null),[limit,setLimit]=useState(80);
 const concepts=(props.concepts||[]).filter(c=>c.source.origin==='SOURCE_SCHEMA'&&[c.preferred_name,c.description].join(' ').toLowerCase().includes(query.toLowerCase()));
 return <><div className="tabs" role="tablist" aria-label="Taxonomy layer"><button role="tab" aria-selected={layer==='policy'} onClick={()=>setLayer('policy')}>Policy classification</button><button role="tab" aria-selected={layer==='schema'} onClick={()=>setLayer('schema')}>Spreadsheet reference dictionary</button></div>
 {layer==='policy'?<PolicyTaxonomy {...props}/>:<Panel title="Spreadsheet reference dictionary" sub="Read-only entities and attributes supplied by the source spreadsheet."><label>Search reference<input value={query} onChange={e=>{setQuery(e.target.value);setLimit(80)}}/></label><p>{concepts.length} source concepts</p>{concepts.slice(0,limit).map(c=><button className="concept-row" key={c.concept_id} onClick={()=>setSelected(c)}><strong>{c.preferred_name}</strong><span>{c.kind}</span></button>)}{concepts.length>limit&&<button onClick={()=>setLimit(n=>n+80)}>Show 80 more</button>}{selected&&<div><h3>{selected.preferred_name}</h3><p>{selected.description}</p><p>Allowed values: {selected.allowed_values.join(', ')||'Not supplied'}</p><Source source={selected.source} onDocument={props.showSource}/></div>}</Panel>}</>;
}
