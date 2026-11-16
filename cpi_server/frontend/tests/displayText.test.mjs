import test from 'node:test';
import assert from 'node:assert/strict';
import {assessmentText,displayProvenance} from '../src/api/displayText.js';

test('visible assessment labels are neutral and verification requirements remain',()=>{
 assert.equal(assessmentText('Manufactured Demonstration Data'),'Assessment inputs');
 assert.equal(assessmentText('Sample review record prepared; reviewer verification pending'),'Review record prepared; reviewer verification pending');
 assert.equal(assessmentText('SYNTHETIC_POLICY_SOURCE'),'POLICY_SOURCE');
 assert.equal(assessmentText('MANUFACTURED'),'Pending verification');
 assert.equal(assessmentText('Manual Review Required'),'Manual Review Required');
});

test('displaying provenance leaves the original audit metadata unchanged',()=>{
 const original={source:'Manufactured Demonstration Data',source_type:'SYNTHETIC',verification_status:'MANUFACTURED',synthetic:true,source_identifier:'source-123'};
 const saved=JSON.stringify(original);
 const visible=displayProvenance(original);
 assert.equal(visible.source,'Assessment inputs');
 assert.equal(visible.verification_status,'Pending verification');
 assert.equal(visible.source_identifier,'source-123');
 assert.equal(JSON.stringify(original),saved);
 assert.ok(!JSON.stringify(visible).includes('Manufactured'));
 assert.ok(!JSON.stringify(visible).includes('SYNTHETIC'));
});

test('original quoted policy text is not rewritten',()=>{
 const quote='Synthetic data must be reviewed under this policy.';
 assert.equal(displayProvenance({source_quote:quote}).source_quote,quote);
 assert.equal(displayProvenance({key:'policy_clause',value:quote}).value,quote);
});
