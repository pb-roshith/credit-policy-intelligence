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
