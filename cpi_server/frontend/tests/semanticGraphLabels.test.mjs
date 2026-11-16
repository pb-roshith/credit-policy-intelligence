import test from 'node:test';
import assert from 'node:assert/strict';
import {graphNodeLabel,relationshipLabel,wrapGraphLabel} from '../src/features/riskKnowledge/graph/labels.js';
test('graph shows actual threshold operators, values and units',()=>{
 assert.equal(graphNodeLabel({type:'Threshold',payload:{operator:'LTE',value:75,unit:'%'},label:'LTE 75 %'}),'≤ 75%');
 assert.equal(graphNodeLabel({type:'Condition',payload:{field:'loan_amount',operator:'GT',value:50,unit:'lakh'},label:'amount'}),'loan amount > 50 lakh');
 assert.equal(graphNodeLabel({type:'Threshold',label:'GTE 75 %'}),'≥ 75 %');
 assert.equal(relationshipLabel('REQUIRES_APPROVAL_FROM'),'requires approval from');
});
test('graph labels wrap and preserve the full policy name when it fits',()=>{
 const label='Maximum home loan LTV for salaried borrowers';
 assert.equal(wrapGraphLabel(label).join(' '),label);
 assert.ok(wrapGraphLabel('A '.repeat(90)).length<=3);
});
