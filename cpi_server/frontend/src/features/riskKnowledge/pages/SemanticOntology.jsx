import React,{useEffect,useState} from 'react';
import {api} from '../services/api';
import {Panel,Badge} from '../components/ui';
import {API} from '../../../api/client';

export default function SemanticOntology() {
 const [model,setModel]=useState(null),[error,setError]=useState(''),[selectedLayer,setSelectedLayer]=useState('');
 const layer=model?.layers?.find(item=>item.name===selectedLayer);
 useEffect(()=>{let active=true;api('/semantic-model').then(d=>{if(active)setModel(d)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[]);
 async function download(kind){try{setError('');const data=await api('/export/'+(kind==='model'?'ontology':kind));const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=kind==='schema'?'instances.schema.json':kind==='example'?'illustrative-example.json':'semantic-model.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){setError(e.message)}}
 return <>
  {error&&<div role="alert" className="notice error">{error}</div>}
  {!model?<p role="status">Loading semantic schema…</p>:<>
   <Panel title="Credit policy business ontology" sub={'Version '+model.version+' · '+model.namespace} action={<Badge>{model.status}</Badge>}>
    <p>A machine-readable definition of business concepts, relationships and validation constraints. Populated values and source evidence are available in the knowledge graph.</p>
    <div className="knowledge-counts"><span><b>{Object.keys(model.classes).length}</b> classes</span><span><b>{Object.keys(model.relationships).length}</b> relationship types</span><span><b>{model.semantic_constraints.length}</b> semantic constraint groups</span></div>
    <div className="button-row"><button onClick={()=>download('model')}>Download semantic model JSON</button><button onClick={()=>download('schema')}>Download JSON Schema</button><a className="button" href={API+'/api/risk-knowledge/semantic-model/ontology.ttl'} target="_blank" rel="noreferrer">Open OWL ontology</a><a className="button" href={API+'/api/risk-knowledge/semantic-model/shapes.ttl'} target="_blank" rel="noreferrer">Open SHACL shapes</a></div>
   </Panel>
   {model.layers&&<Panel title="Ontology layers" sub={layer?.description}>
    <label>Show layer <select value={selectedLayer} onChange={event=>setSelectedLayer(event.target.value)}>
     <option value="">All layers</option>{model.layers.map(item=><option key={item.name}>{item.name}</option>)}
    </select></label>
   </Panel>}
   <Panel title="Business classes"><div className="policy-taxonomy-table"><table><thead><tr><th>Class</th><th>Definition</th><th>Properties</th></tr></thead><tbody>{Object.entries(model.classes).filter(([name])=>!layer||layer.classes.includes(name)).map(([name,c])=><tr key={name}><td><strong>{name}</strong>{c.parent&&<small>Subclass of {c.parent}</small>}</td><td>{c.definition}</td><td>{Object.keys(c.properties).map(p=><div key={p}><code>{p}</code>{c.required_properties.includes(p)?' (required)':''}</div>)}</td></tr>)}</tbody></table></div></Panel>
   <Panel title="Typed relationships" sub="Counts apply per subject. Missing optional scope or dates do not establish unrestricted applicability or current validity."><div className="policy-taxonomy-table"><table><thead><tr><th>Relationship</th><th>From</th><th>To</th><th>Count</th><th>Meaning</th></tr></thead><tbody>{Object.entries(model.relationships).filter(([name])=>!layer||layer.relationships.includes(name)).map(([name,r])=><tr key={name}><td><code>{name}</code></td><td>{r.domain.join(' or ')}</td><td>{r.range.join(' or ')}</td><td>{r.min_per_subject}..{r.max_per_subject??'*'}</td><td>{r.definition}</td></tr>)}</tbody></table></div></Panel>
   <Panel title="Validation and integration"><ul>{model.semantic_constraints.map(c=><li key={c.code}><strong>{c.code}</strong>: {c.definition}</li>)}</ul><p>{model.taxonomic_integration}</p><p>{model.operational_integration}</p><p>{model.approval_semantics}</p><p>JSON Schema validates individual records. The supplied semantic validator also checks cross-record relationships and provenance. SHACL provides the RDF validation profile.</p></Panel>
  </>}
 </>;
}
