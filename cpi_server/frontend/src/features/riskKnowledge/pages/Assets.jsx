import React from 'react';
import {Panel,Badge,Empty} from '../components/ui';
export default function Assets({state,showSource,onOpenRules}) {
 const policies=state.documents.filter(d=>d.document_type==='policy');
 const references=state.documents.filter(d=>d.document_type!=='policy');
 return <><Panel title="Policy source documents" sub="The same registered policies supply taxonomy, extracted rules, policy evidence and the knowledge graph.">
 <button onClick={onOpenRules}>Open Policy Rule Library</button>
 {!policies.length&&<Empty>No registered policy sources.</Empty>}
 {policies.map(d=><article className="asset-row" key={d.document_id}><div><h3>{d.document_name}</h3><p>Version {d.version} - Effective {d.effective_date||'Not supplied'}</p><Badge>POLICY_SOURCE</Badge></div><button onClick={()=>showSource(d.document_id)}>View source</button></article>)}</Panel>
 <Panel title="Reference dictionaries" sub="Spreadsheet entities and attributes support the controlled vocabulary. Policy values and rules come from policy passages.">{references.map(d=><article className="asset-row" key={d.document_id}><strong>{d.document_name}</strong><button onClick={()=>showSource(d.document_id)}>View reference</button></article>)}</Panel></>;
}
