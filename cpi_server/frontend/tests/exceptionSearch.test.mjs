import test from 'node:test';
import assert from 'node:assert/strict';
import { filterExceptions } from '../src/api/exceptionSearch.js';

const rows = [
  { id: 'EX-9001', credit_request_number: 'CR-10241', type: 'Collateral', clause: 'COL-2.1', severity: 'High', exposure: 25000000, owner: 'Manager A', account_user_id: 'manager_a', status: 'Active' },
  { id: 'EX-9002', credit_request_number: 'deal_abc', type: 'Tenor', owner: 'Manager B', account_user_id: 'manager_b', status: 'Closed' },
  { id: 'EX-9003', credit_request_number: null, status: 'Active' },
];

test('search finds exception ID and every searchable registry field', () => {
  for (const query of ['EX-9001', 'cr-10241', 'collateral', 'COL-2.1', 'high', '$25M', 'Manager A', 'manager_a', 'CR-10241@manager_a']) {
    assert.deepEqual(filterExceptions(rows, 'All', ` ${query} `), [rows[0]], query);
  }
  assert.deepEqual(filterExceptions(rows, 'All', 'deal_abc'), [rows[1]]);
});

test('search respects status tabs, handles missing IDs', () => {
  assert.deepEqual(filterExceptions(rows, 'Active', 'collateral'), [rows[0]]);
  assert.deepEqual(filterExceptions(rows, 'Closed', 'EX-9001'), []);
  assert.deepEqual(filterExceptions(rows, 'All', 'EX-9003'), [rows[2]]);
  assert.deepEqual(filterExceptions(rows, 'All', 'no such exception'), []);
});

test('clearing search restores all records in the selected tab', () => {
  assert.deepEqual(filterExceptions(rows, 'All', '   '), rows);
  assert.deepEqual(filterExceptions(rows, 'Active', ''), [rows[0], rows[2]]);
});
