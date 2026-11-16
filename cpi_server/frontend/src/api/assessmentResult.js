// The findings table shows the actual-versus-threshold result. Scope and manual
// review requirements remain in the original finding and its evidence details.
import {policyRuleCategory} from './policyRuleCategory.js';

export function assessmentFindingKey(finding) {
  return JSON.stringify([
    finding.request_id ?? '', finding.policy_id ?? '',
    finding.rule_version_id ?? finding.rule_id ?? [finding.clause_id, finding.rule_name || finding.policy_clause],
    finding.entity_id ?? '',
  ]);
}

export function assessmentResult(finding, definition = {}) {
  const result = String(finding.result || finding.severity || '').toLowerCase();
  const known = { pass: 'Pass', warning: 'Warning', breach: 'Breach' };
  if (known[result]) return known[result];

  const comparison = finding.threshold_comparison;
  if (!comparison || typeof comparison.condition_met !== 'boolean') {
    return 'Unable to Assess';
  }
  const thresholdType = String(definition.threshold_type || finding.threshold_type || '').toUpperCase();
  const severity = String(definition.severity || finding.severity || '').toUpperCase();
  // Warning and breach triggers describe an adverse condition; hard limits
  // describe a condition the request must satisfy.
  if (['WARNING', 'EARLY_WARNING', 'WARNING_TRIGGER'].includes(thresholdType)) {
    return comparison.condition_met ? 'Warning' : 'Pass';
  }
  if (['BREACH', 'BREACH_TRIGGER'].includes(thresholdType)) {
    return comparison.condition_met ? 'Breach' : 'Pass';
  }
  return comparison.condition_met ? 'Pass' : severity === 'WARNING' ? 'Warning' : 'Breach';
}

export function assessmentFindings(review) {
  const definitions = new Map((review?.rule_snapshots || []).map(rule => [String(rule.id), rule.definition]));
  const snapshots = new Map((review?.rule_snapshots || []).map(rule => [String(rule.id), rule]));
  return (review?.findings || []).map(finding => ({ ...finding,
    rule_category:policyRuleCategory(finding.rule_category||finding.rule_type?finding:snapshots.get(String(finding.rule_version_id))||finding),
    displayResult: review.assessment_scope==='current-semantic-graph'?finding.result:assessmentResult(finding, definitions.get(String(finding.rule_version_id))),
  }));
}
