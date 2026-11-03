import test from 'node:test';
import assert from 'node:assert/strict';
import { extractionProgress } from '../src/api/extractionProgress.js';

test('counts completed documents out of the selected ten', () => {
  const result = extractionProgress({policy_ids: [1,2,3,4,5,6,7,8,9,10], progress: [
    {policy_id: 1, status: 'Completed'}, {policy_id: 2, status: 'Completed'},
    {policy_id: 3, status: 'Running', completed_batches: 5}
  ]});
  assert.deepEqual(result, {total: 10, completed: 2, failed: 0, processed: 2});
});

test('counts partial extraction and zero-rule outcomes as completed documents', () => {
  assert.deepEqual(extractionProgress({policy_ids: [1,2], progress: [
    {policy_id: 1, status: 'Failed', rules_proposed: 5}, {policy_id: 2, status: 'Failed', rules_proposed: 0}
  ]}), {total: 2, completed: 2, failed: 2, processed: 2});
});

test('uses the latest result per document and ignores unrelated documents', () => {
  assert.deepEqual(extractionProgress({policy_ids: [1,1,'2'], progress: [
    {policy_id: 1, status: 'Running'}, {policy_id: '1', status: 'Completed'},
    {policy_id: 2, status: 'Already processed'}, {policy_id: 99, status: 'Completed'}
  ]}), {total: 2, completed: 2, failed: 0, processed: 2});
});

test('handles a job that has not started', () => {
  assert.deepEqual(extractionProgress(), {total: 0, completed: 0, failed: 0, processed: 0});
});

test('partial documents count as processed and needing retry',()=>{
  assert.deepEqual(extractionProgress({policy_ids:[1],progress:[{policy_id:1,status:'Completed with errors'}]}),
    {total:1,completed:1,failed:1,processed:1});
});
