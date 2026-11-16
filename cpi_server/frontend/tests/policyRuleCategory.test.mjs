import test from 'node:test';
import assert from 'node:assert/strict';
import {policyRuleCategory,filterByRuleCategory} from '../src/api/policyRuleCategory.js';
import {assessmentFindings} from '../src/api/assessmentResult.js';

test('category filters partition every rule, including qualitative exceptions',()=>{
 const rules=[{extracted:{rule_kind:'QUANTITATIVE',thresholds:[{value:75}]}},
  {extracted:{rule_kind:'QUALITATIVE',thresholds:[]}},
  {extracted:{rule_kind:'EXCEPTION_RULE',thresholds:[]}},
  {extracted:{rule_kind:'EXCEPTION_RULE',thresholds:[{value:85}]}}];
 assert.equal(filterByRuleCategory(rules).length,4);
 assert.equal(filterByRuleCategory(rules,'QUALITATIVE').length,2);
 assert.equal(filterByRuleCategory(rules,'QUANTITATIVE').length,2);
 assert.equal(policyRuleCategory({definition:{rule_type:'quantitative'}}),'QUANTITATIVE');
});
test('saved semantic assessments recover categories from their snapshots',()=>{
 const review={assessment_scope:'current-semantic-graph',findings:[{rule_version_id:'r1',result:'Pass'},
  {rule_version_id:'r2',result:'Manual Review Required'}],rule_snapshots:[
  {id:'r1',semantic_rule:{extracted:{rule_kind:'QUANTITATIVE'}}},
  {id:'r2',semantic_rule:{extracted:{rule_kind:'EXCEPTION_RULE'}}}]};
 const rows=assessmentFindings(review);
 assert.deepEqual(rows.map(r=>r.rule_category),['QUANTITATIVE','QUALITATIVE']);
 assert.equal(filterByRuleCategory(rows,'QUALITATIVE')[0].result,'Manual Review Required');
 assert.equal(review.findings[0].rule_category,undefined);
});
