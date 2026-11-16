import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {filterByRuleCategory} from '../src/api/policyRuleCategory.js';
import {assessmentFindingKey} from '../src/api/assessmentResult.js';

test('category switches keep unique table row identities when actual text repeats',async()=>{
 const server=await createServer({cacheDir:'node_modules/.vite-tests/'+process.pid,optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 try {
  const {default:FindingsTable}=await server.ssrLoadModule('/src/components/ComplianceFindingsTable.jsx');
  const findings=[
   {rule_version_id:'r1',policy_id:1,rule_name:'Operational Oversight and Compliance Reporting by Collateral Management Unit',rule_category:'QUALITATIVE'},
   {rule_version_id:'r2',policy_id:1,rule_name:'Staff training',rule_category:'QUALITATIVE'},
   {rule_version_id:'r3',policy_id:1,rule_name:'Maximum LTV',rule_category:'QUANTITATIVE'},
   {rule_version_id:'r4',policy_id:2,rule_name:'Maximum LTV',rule_category:'QUANTITATIVE'},
  ].map(f=>({...f,actual:'Sample review record prepared; reviewer verification pending'}));
  const keysByRule=new Map();
  for(const category of ['ALL','QUANTITATIVE','QUALITATIVE','QUANTITATIVE','ALL']){
   const filtered=filterByRuleCategory(findings,category);
   const rows=filtered.map(f=>[f.rule_name,f.actual,'Requirement',null,'Manual Review Required',f]);
   const element=FindingsTable({rows,onPolicy:()=>{},onEvidence:()=>{}});
   assert.equal(typeof element.props.rowKey,'function');
   // Inspect the actual DataTable row elements, not just the filtered array.
   const table=element.type(element.props);
   const body=table.props.children.props.children.find(child=>child.type==='tbody');
   const keys=body.props.children.map(child=>child.key);
   assert.equal(new Set(keys).size,rows.length);
   rows.forEach((row,i)=>{
    const id=row[5].rule_version_id;
    if(keysByRule.has(id))assert.equal(keys[i],keysByRule.get(id));
    keysByRule.set(id,keys[i]);
    if(category==='QUANTITATIVE')assert.equal(row[5].rule_category,'QUANTITATIVE');
   });
  }
  assert.equal(assessmentFindingKey(findings[0]),assessmentFindingKey({...findings[0],actual:'Changed observation'}));
 } finally {await server.close()}
});
