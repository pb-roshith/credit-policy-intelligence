import test from 'node:test';
import assert from 'node:assert/strict';
import { assessmentResult, assessmentFindings } from '../src/api/assessmentResult.js';

const demo = met => ({ result: 'Manual Review Required', applicability: 'Applicable',
  threshold_comparison: { condition_met: met } });

test('preserves authoritative assessment outcomes', () => {
  for (const status of ['Pass', 'Warning', 'Breach']) {
    assert.equal(assessmentResult({ result: status }), status);
  }
  assert.equal(assessmentResult({ severity: 'PASS' }), 'Pass');
});

test('semantic graph assessments preserve manual and unresolved results without legacy reinterpretation',()=>{
 const review={assessment_scope:'current-semantic-graph',findings:[{result:'Manual Review Required'},{result:'Unable to Assess'},{result:'Breach'}]};
 assert.deepEqual(assessmentFindings(review).map(f=>f.displayResult),['Manual Review Required','Unable to Assess','Breach']);
});

test('classifies manufactured actuals against hard limits', () => {
  assert.equal(assessmentResult(demo(true)), 'Pass');
  assert.equal(assessmentResult(demo(false)), 'Breach');
  assert.equal(assessmentResult(demo(false), { severity: 'WARNING' }), 'Warning');
});

test('warning and breach triggers fire when their condition is met', () => {
  for (const [threshold_type, outcome] of [['WARNING', 'Warning'], ['BREACH_TRIGGER', 'Breach']]) {
    assert.equal(assessmentResult(demo(true), { threshold_type }), outcome);
    assert.equal(assessmentResult(demo(false), { threshold_type }), 'Pass');
  }
});

test('missing threshold comparisons show Unable to Assess', () => {
  for (const finding of [
    { result: 'Manual Review Required' }, { result: 'Unable to Assess' }, {},
    { ...demo(true), threshold_comparison: { condition_met: null } },
  ]) assert.equal(assessmentResult(finding), 'Unable to Assess');
});

test('600 million against a 500 million maximum is Breach despite missing client tier', () => {
  const finding = {
    rule_version_id: 3787,
    result: 'Unable to Assess',
    applicability: 'Unable to Determine Applicability',
    missing_inputs: ['client_tier', 'requirement.client_tier'],
    actual: '600.0', actual_unit: 'USD million', observed_value: 600,
    threshold_comparison: { actual: 600, operator: 'less_than_or_equal',
      threshold: 500, unit: 'USD million', condition_met: false, source_type: 'SYNTHETIC' },
  };
  const review = { findings: [finding], rule_snapshots: [
    { id: 3787, definition: { threshold_type: 'HARD_LIMIT' } },
  ] };
  assert.equal(assessmentFindings(review)[0].displayResult, 'Breach');
  assert.equal(finding.result, 'Unable to Assess');
  assert.deepEqual(finding.missing_inputs, ['client_tier', 'requirement.client_tier']);
});

test('a completed numeric comparison is not hidden by unrelated manual-review metadata', () => {
  assert.equal(assessmentResult({ ...demo(true),
    applicability: 'Unable to Determine Applicability', missing_inputs: ['client_tier'] }), 'Pass');
  assert.equal(assessmentResult({ ...demo(false),
    missing_inputs: ['Unresolved AND requirement'] }), 'Breach');
});

test('dual-review haircut screenshot shows Warning when the 30% trigger is exceeded', () => {
  const finding = { result: 'Unable to Assess', actual: '36.0', observed_value: 36,
    threshold_type: 'WARNING_TRIGGER', threshold_comparison: {
      actual: 36, threshold: 30, operator: 'greater_than', condition_met: true,
    } };
  assert.equal(assessmentResult(finding, { threshold_type: null, operator: null }), 'Warning');
  assert.equal(assessmentResult({ ...finding,
    threshold_comparison: { ...finding.threshold_comparison, actual: 30, condition_met: false } }), 'Pass');
});

test('uses saved rule definitions without changing underlying findings', () => {
  const finding = { ...demo(true), rule_version_id: 7 };
  const findings = assessmentFindings({ findings: [finding],
    rule_snapshots: [{ id: 7, definition: { threshold_type: 'WARNING' } }] });
  assert.equal(findings[0].displayResult, 'Warning');
  assert.equal(finding.result, 'Manual Review Required');
  assert.equal(finding.displayResult, undefined);
  assert.deepEqual(assessmentFindings(null), []);
});
