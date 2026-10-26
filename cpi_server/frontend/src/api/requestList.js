import { workbenchRequests } from "./workbenchRows.js";

// Both request screens use the same sources, deduplication and ordering.
export async function loadRequestList(token, request) {
  const [dealResult, legacyResult] = await Promise.allSettled([
    request("/api/deals", {}, token),
    request("/api/requests", {}, token),
  ]);
  return {
    rows: workbenchRequests(
      dealResult.status === "fulfilled" ? dealResult.value.deals : [],
      legacyResult.status === "fulfilled" ? legacyResult.value : [],
    ),
    error: dealResult.status === "rejected" ? dealResult.reason.message
      : legacyResult.status === "rejected" ? legacyResult.reason.message : "",
  };
}
