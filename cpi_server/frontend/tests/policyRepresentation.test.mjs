import test from 'node:test';
import assert from 'node:assert/strict';
import {formatPolicyCondition,describePolicyRequirement,filterPolicyCoverage} from '../src/api/policyRepresentation.js';
test('human-readable rule preserves shared property and programme conditions',()=>{
 const scope={all:[{field:'property_type',operator:'equals',value:'Investment Property'},{field:'loan_program',operator:'equals',value:'Government-Insured'}]};
 assert.equal(formatPolicyCondition(scope),'(Property type is Investment Property AND Loan programme is Government-Insured)');
 assert.equal(describePolicyRequirement({metric:'ltv',operator:'less_than_or_equal',threshold:75,unit:'%'}),'LTV ≤ 75%');
});
test('nested property alternatives remain grouped before the programme condition',()=>{
 const scope={all:[{any:[{field:'property_type',operator:'equals',value:'Secondary Residence'},{field:'property_type',operator:'equals',value:'Vacation Home'}]},{field:'loan_program',operator:'equals',value:'Conventional'}]};
 assert.equal(formatPolicyCondition(scope),'((Property type is Secondary Residence OR Property type is Vacation Home) AND Loan programme is Conventional)');
});
test('requirements and attention lists do not ask users to approve document furniture',()=>{
 const coverage=['VALIDATED','NON_RULE','UNRESOLVED','LLM_PROPOSED','REVIEWED'].map(status=>({status}));
 assert.deepEqual(filterPolicyCoverage(coverage,'REQUIREMENTS').map(r=>r.status),['VALIDATED','REVIEWED']);
 assert.deepEqual(filterPolicyCoverage(coverage,'ATTENTION').map(r=>r.status),['UNRESOLVED','LLM_PROPOSED']);
});
