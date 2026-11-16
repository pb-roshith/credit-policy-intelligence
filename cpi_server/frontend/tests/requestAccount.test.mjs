import test from 'node:test';
import assert from 'node:assert/strict';
import { prepareAccountRequest } from '../src/api/requestAccount.js';

test('identical local IDs target the selected manager for GET and POST', () => {
  const get = prepareAccountRequest('/api/compliance-review/CR-10241%40manager_a/latest');
  assert.equal(get.path, '/api/compliance-review/CR-10241/latest');
  assert.equal(get.account, 'manager_a');
  const post = prepareAccountRequest('/api/compliance-review/run', { method: 'POST', body: JSON.stringify({ credit_request_number: 'CR-10241@manager_b' }) });
  assert.equal(post.account, 'manager_b');
  assert.equal(JSON.parse(post.options.body).credit_request_number, 'CR-10241');
});

test('shared deal IDs and existing URL query strings are preserved', () => {
  const result = prepareAccountRequest('/api/requests?status=In%20Review');
  assert.equal(result.path, '/api/requests?status=In%20Review');
  assert.equal(result.account, undefined);
  const shared = prepareAccountRequest('/api/compliance-review/deal_abc/latest');
  assert.equal(shared.path, '/api/compliance-review/deal_abc/latest');
  assert.equal(shared.account, undefined);
});

test('a batch cannot accidentally target the wrong manager', () => {
  assert.throws(() => prepareAccountRequest('/api/data-manufacturing/exceptions', { body: JSON.stringify({ credit_request_numbers: ['CR-1@manager_a', 'CR-1@manager_b'] }) }), /one account/);
});

test('simulator query parameters select the manager account and remove the display suffix',()=>{
 const result=prepareAccountRequest('/api/decision-scenarios/request-context?credit_request_number=CR-10241%40manager_a');
 assert.equal(result.account,'manager_a');
 assert.equal(result.path,'/api/decision-scenarios/request-context?credit_request_number=CR-10241');
 const detail=prepareAccountRequest('/api/decision-scenarios/12?credit_request_number=CR-10241%40manager_b');
 assert.equal(detail.account,'manager_b');
 assert.equal(new URL(detail.path,'http://local').searchParams.get('credit_request_number'),'CR-10241');
});

test('conflicting query/body manager scopes are rejected and opaque deal IDs stay unchanged',()=>{
 assert.throws(()=>prepareAccountRequest('/api/decision-scenarios?credit_request_number=CR-1%40manager_a',{
  body:JSON.stringify({credit_request_number:'CR-1@manager_b'})}),/one account/);
 const shared=prepareAccountRequest('/api/decision-scenarios/request-context?credit_request_number=deal_AbC%40tenant');
 assert.equal(shared.account,undefined);
 assert.equal(new URL(shared.path,'http://local').searchParams.get('credit_request_number'),'deal_AbC@tenant');
});
