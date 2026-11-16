import test from 'node:test';
import assert from 'node:assert/strict';
import {scenarioContextPath,scenarioListPath,scenarioDetailPath,scenarioUnlinkedPath,scenarioRequestNumber,scenarioInputs,scenarioPayload} from '../src/api/scenarioRequests.js';

test('every simulator read is scoped to the selected request, retaining opaque ID case',()=>{
 const id='deal_AbC+&42';
 for(const path of [scenarioContextPath(id),scenarioListPath(id),scenarioDetailPath(9,id),scenarioUnlinkedPath(id)])assert.equal(new URL(path,'http://local').searchParams.get('credit_request_number'),id);
 assert.throws(()=>scenarioListPath(''));assert.throws(()=>scenarioDetailPath(9,''));
});

test('qualified list selections match the plain request number returned in account-scoped responses',()=>{
 assert.equal(scenarioRequestNumber('CR-10241@manager_a'),'CR-10241');
 assert.equal(scenarioRequestNumber('CR-10241@manager_b'),'CR-10241');
 assert.equal(scenarioRequestNumber('deal_AbC@tenant'),'deal_AbC@tenant');
});
test('baseline amount and units are retained and every scenario submission carries request identity',()=>{
 const context={currency:'INR',inputs:{facility_amount:0.5,collateral_coverage:110,risk_rating:'BB+',pricing_bps:275,tenor_years:1.5,covenants:'Full'}};
 const inputs=scenarioInputs(context);
 assert.equal(inputs.facility_amount,0.5);assert.equal(inputs.currency,'INR');assert.equal(inputs.tenor_years,1.5);
 const payload=scenarioPayload('deal_AbC','Downside',{...inputs,facility_amount:0.6});
 assert.equal(payload.credit_request_number,'deal_AbC');assert.equal(payload.facility_amount,0.6);assert.equal(payload.currency,'INR');
 assert.equal(context.inputs.facility_amount,0.5);assert.throws(()=>scenarioPayload('','Downside',inputs));
});
