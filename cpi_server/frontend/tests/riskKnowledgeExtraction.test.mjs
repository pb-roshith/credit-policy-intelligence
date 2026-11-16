import test from 'node:test';
import assert from 'node:assert/strict';
import {extractionPolicyIds,ruleExtractionSummary} from '../src/api/riskKnowledgeExtraction.js';

test('graph extraction reports unresolved coverage even when no rule can compile',()=>{
 const result=ruleExtractionSummary({status:'Failed',report:{pipeline:'policy-graph-first-v1',rules_proposed:0,unresolved_spans:7}});
 assert.equal(result.status,'Completed with errors');
 assert.match(result.message,/0 drafts compiled.*7 source passages.*cannot execute/);
});

test('complete graph coverage does not claim drafts are operationally approved',()=>{
 const result=ruleExtractionSummary({status:'Completed',report:{pipeline:'policy-graph-first-v1',rules_proposed:3,unresolved_spans:0}});
 assert.match(result.message,/3 drafts.*approval is still required/);
});

test('saved rules retain partial failures and allow retry',()=>{
  const result=ruleExtractionSummary({status:'Completed with errors',report:{rules_proposed:23},progress:[{error:'source error',unresolved_mappings:64}]});
  assert.equal(result.status,'Completed with errors');
  assert.match(result.message,/23 rules extracted.*Retry extraction/);
});

test('fully successful extraction shows completed',()=>{
  assert.deepEqual(ruleExtractionSummary({status:'Completed',report:{rules_proposed:23}}),
    {status:'Completed',message:'23 rules extracted.'});
});

test('worker-level error is visible even without a failed policy entry',()=>{
  const result=ruleExtractionSummary({status:'Failed',error:'Worker interrupted; retry resumes completed batches'});
  assert.match(result.message,/Worker interrupted/);
});

test('historical jobs with hidden partial results remain retryable',()=>{
  const result=ruleExtractionSummary({status:'Completed',report:{rules_proposed:2},progress:[{status:'Completed',partial_result:true}]});
  assert.equal(result.status,'Completed with errors');
});
test('zero results cannot be presented as successful extraction',()=>{
  assert.equal(ruleExtractionSummary({status:'Failed',report:{rules_proposed:0}}).status,'Failed');
  assert.equal(ruleExtractionSummary({status:'Running'}),null);
});

test('failed taxonomy job explains incomplete AI data using its stage label',()=>{
  const result=ruleExtractionSummary({status:'Failed',report:{rules_proposed:0},progress:[{
    status:'Failed',stage:'taxonomy',stages:[{id:'taxonomy',label:'Taxonomy proposals',status:'Failed'}],
    error:'Unterminated string starting at: line 1 column 37386 (char 37385)'
  }]});
  assert.equal(result.status,'Failed');
  assert.equal(result.message,'No rules were extracted. Taxonomy proposals failed: The AI returned incomplete or invalid data. Retry extraction.');
});

test('failed extraction retains a specific non-JSON failure reason',()=>{
  const result=ruleExtractionSummary({status:'Failed',progress:[{status:'Failed',error:'Source document not found'}]});
  assert.match(result.message,/Source document not found/);
});

test('the policy dropdown drives Extract Rules when a policy is selected',()=>{
  assert.deepEqual(extractionPolicyIds('7',[1,2]),[7]);
});
test('all-policies view uses only explicitly checked documents',()=>{
  assert.deepEqual(extractionPolicyIds('',[1,'2',1]),[1,2]);
  assert.deepEqual(extractionPolicyIds('',[]),[]);
});
test('invalid policy selection cannot turn into extracting all documents',()=>{
  assert.deepEqual(extractionPolicyIds('bad',[1,2]),[]);
  assert.deepEqual(extractionPolicyIds('',[0,-1,Infinity,2.5]),[]);
});
