import React from 'react';
import {assessmentText} from '../api/displayText';
import {ExternalLink} from 'lucide-react';
import {Badge,DataTable} from './ui';
import {assessmentFindingKey} from '../api/assessmentResult';

export default function ComplianceFindingsTable({rows,onPolicy,onEvidence}) {
 return <DataTable className="findings-table" headers={["Policy Clause","Actual","Threshold","Variance","Result","Evidence"]}
  rows={rows} rowKey={row=>assessmentFindingKey(row[5])}
  render={(value,index,row)=>index===0?<div className="finding-clause"><strong>{value}</strong><small>{row[5].policy_name}</small><small>{row[5].rule_category==='QUANTITATIVE'?'Quantitative':'Qualitative'}</small></div>:index===1?<div>{assessmentText(value)} {row[5].actual_unit}{!row[5].actual_sources?.includes("SYNTHETIC")&&<small>{assessmentText(row[5].actual_sources?.join(", "))}</small>}</div>:index===4?<Badge>{value}</Badge>:index===5?<div><button className="trace" title={row[5].evidence} onClick={()=>onPolicy(row[5])}>Policy <ExternalLink size={12}/></button><button className="trace" onClick={()=>onEvidence(row[5])}>Evidence and matching trace</button></div>:value}/>;
}
