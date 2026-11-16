// Read-only display mapping. Assumptions never change a Dossier deal or CPI record.
const hasNumber = value => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
const statusMap = { Draft: "Pending", "In Progress": "In Review", "Changes Requested": "Escalated", Exported: "Approved" };

export function dossierRequest(deal, existing) {
  const intake = deal.intake || {};
  const assumptions = [];
  const value = (label, supplied, fallback) => {
    if (supplied !== null && supplied !== undefined && supplied !== "") return supplied;
    assumptions.push(label);
    return fallback;
  };
  const number = (label, supplied, fallback) => value(label, hasNumber(supplied) ? Number(supplied) : null, fallback);
  const amount = number("Requested amount", deal.amount, 1000000);
  const currency = value("Currency", deal.currency, "USD");
  const comparable = !existing?.currency ? currency === "USD" : existing.currency === currency;
  const exposure = number("Exposure", deal.exposure ?? (comparable ? existing?.exposure : null), Math.round(amount * 0.6));
  const rating = value("Rating", deal.rating || intake.rating || existing?.rating, "BBB");
  const coverage = number("Collateral coverage", deal.collateral_coverage ?? intake.collateral_coverage ?? existing?.collateral_coverage, deal.collateral === false ? 0 : 100);
  const compliance = existing?.assessment_scope === 'current-semantic-graph' ? existing.compliance_score : null;
  const pricingMatch = /([0-9]+(?:\.[0-9]+)?)\s*bps/i.exec(deal.pricing || "");
  const pricing = number("Recommended pricing", deal.recommended_pricing_bps ?? existing?.recommended_pricing_bps ?? pricingMatch?.[1], 275);
  const tenor = number("Recommended tenor", hasNumber(deal.tenure) && Number(deal.tenure) > 0 ? Number(deal.tenure) / 12 : existing?.recommended_tenor_years, 5);
  const risks = [];
  if (rating.startsWith("BB") && !rating.startsWith("BBB")) risks.push(`Borrower rating ${rating} warrants closer credit-risk review.`);
  if (coverage < 120) risks.push(`Collateral coverage is ${coverage}%; confirm collateral value and security terms.`);
  if (deal.kyc !== "verified") risks.push("KYC verification is pending or not recorded on the deal.");
  if (assumptions.length) risks.push("Missing deal data has been assumed for this workbench view; validate it before making a credit decision.");
  if (!risks.length) risks.push("Confirm borrower financials, repayment capacity and policy conditions before approval.");
  return {
    shared_deal_id: deal.id, credit_request_number: deal.id,
    borrower_name: deal.customer, industry: value("Industry", deal.industry, "Manufacturing"),
    geography: value("Geography", deal.geography, "Asia Pacific"),
    exposure, facility: value("Facility", deal.facility, "Term Loan"), rating,
    requested_amount: amount, currency, status: statusMap[deal.status] || deal.status || "Pending",
    compliance_score: compliance, assessment_scope: existing?.assessment_scope, compliance_status: existing?.compliance_status, collateral_coverage: coverage,
    recommended_pricing_bps: pricing, recommended_tenor_years: tenor,
    assistant: {
      summary: intake.summary || "", risks, assumptions,
      actions: ["Validate borrower financials and all assumed values.", "Confirm KYC, collateral and required supporting documents.",
                "Review applicable policy conditions and obtain delegated approval."],
    },
  };
}

export function workbenchRequests(deals, legacy, summaries=[]) {
  const latest=new Map(summaries.map(r=>[r.request_id,r]));
  const byId = new Map(legacy.filter(row => row.shared_deal_id).map(row => [row.shared_deal_id, row]));
  const sourceIds = new Set(deals.map(deal => deal.id));
  return [...deals.map(deal => dossierRequest(deal, latest.get(deal.id)||byId.get(deal.id))),
    ...legacy.filter(row => !sourceIds.has(row.shared_deal_id))]
    .sort((a, b) => (a.compliance_score ?? Infinity) - (b.compliance_score ?? Infinity));
}
