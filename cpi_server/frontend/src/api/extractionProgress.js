export function extractionProgress(job) {
  const selected = new Set((job?.policy_ids || []).map(String));
  const results = new Map((job?.progress || [])
    .filter(item => selected.has(String(item.policy_id)))
    .map(item => [String(item.policy_id), item.status]));
  const completed = [...results.values()].filter(status => ["Completed", "Already processed", "Failed"].includes(status)).length;
  const failed = [...results.values()].filter(status => status === "Failed").length;
  return { total: selected.size, completed, failed, processed: completed };
}
