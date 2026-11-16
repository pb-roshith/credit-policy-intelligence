import test from 'node:test';
import assert from 'node:assert/strict';
import {filterSemanticPassages, formatExtractedConditions, describeExtractedRequirement} from '../src/api/policyRepresentation.js';

test('all passages include background and unprocessed source; rule filter includes supporting context',()=>{
 const passages=[
  {clause_id:1,disposition:'RULES',primary_rule_ids:['r1'],supporting_rule_ids:[],source:{passage:'Maximum spread',section:'Pricing'}},
  {clause_id:2,disposition:'NON_RULE',primary_rule_ids:[],supporting_rule_ids:['r1'],source:{passage:'Background context'}},
  {clause_id:3,disposition:'NOT_PROCESSED',primary_rule_ids:[],supporting_rule_ids:[],source:{passage:'Pending text'}}];
 assert.equal(filterSemanticPassages(passages).length,3);
 assert.deepEqual(filterSemanticPassages(passages,'RULES').map(p=>p.clause_id),[1,2]);
 assert.deepEqual(filterSemanticPassages(passages,'NOT_PROCESSED').map(p=>p.clause_id),[3]);
 assert.equal(filterSemanticPassages(passages,'ALL','PRICING')[0].clause_id,1);
 assert.equal(filterSemanticPassages(passages,'RULES','pending').length,0);
});
test('extracted condition formatting preserves amount units and nested logic',()=>{
 assert.equal(formatExtractedConditions({logic:'AND',conditions:[{field:'loan_amount',operator:'GT',value:50,unit:'lakh'}],groups:[{logic:'OR',conditions:[{field:'segment',operator:'EQ',value:'Salaried'},{field:'segment',operator:'EQ',value:'SME'}]}]}),'loan amount > 50 lakh AND (segment = Salaried OR segment = SME)');
 assert.equal(formatExtractedConditions({logic:'NOT',conditions:[{field:'country',operator:'EQ',value:'India'}]}),'NOT (country = India)');
 assert.equal(formatExtractedConditions(null),'Not stated in this extraction');
});
test('requirements preserve threshold operators and qualitative names',()=>{
 assert.equal(describeExtractedRequirement({name:'LTV limit',metrics:[{key:'ltv',name:'LTV'}],thresholds:[{metric_key:'ltv',operator:'LTE',value:75,unit:'%'}]}),'LTV ≤ 75 %');
 assert.equal(describeExtractedRequirement({name:'Approval required',thresholds:[]}),'Approval required');
});
