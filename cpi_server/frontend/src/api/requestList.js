import { workbenchRequests } from "./workbenchRows.js";

// Both request screens use the same sources, deduplication and ordering.
export async function loadRequestList(token, request) {
  const [dealResult, legacyResult, summaryResult] = await Promise.allSettled([
    request("/api/deals", {}, token),
    request("/api/requests", {}, token),
    request("/api/compliance-review/current-summaries", {}, token),
  ]);
  return {
    rows: workbenchRequests(
      dealResult.status === "fulfilled" ? dealResult.value.deals : [],
      legacyResult.status === "fulfilled" ? legacyResult.value : [],
      summaryResult.status === "fulfilled" ? summaryResult.value : [],
    ),
    error: dealResult.status === "rejected" ? dealResult.reason.message
      : legacyResult.status === "rejected" ? legacyResult.reason.message : "",
  };
}
