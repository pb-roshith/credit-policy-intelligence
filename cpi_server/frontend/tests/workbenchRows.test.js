import test from "node:test";
import assert from "node:assert/strict";
import { dossierRequest, workbenchRequests } from "../src/api/workbenchRows.js";

const deal = { id: "deal_sky", customer: "Example Borrower", industry: "Manufacturing", geography: "India",
  currency: "INR", amount: 100000000, tenure: 60, facility: "Term Loan", status: "Draft", collateral: true };

test("Dossier facts and currency are preserved; missing fields are explicitly assumed", () => {
  const before = structuredClone(deal);
  const row = dossierRequest(deal);
  assert.equal(row.borrower_name, deal.customer);
  assert.equal(row.credit_request_number, deal.id);
  assert.equal(row.currency, "INR");
  assert.equal(row.requested_amount, 100000000);
  assert.equal(row.recommended_tenor_years, 5);
  assert.equal(row.status, "Pending");
  assert.equal(row.rating, "BBB");
  assert.ok(row.assistant.assumptions.includes("Rating"));
  assert.ok(row.assistant.assumptions.includes("Exposure"));
  assert.ok(row.assistant.assumptions.includes("Compliance score"));
  assert.deepEqual(deal, before);
  assert.deepEqual(dossierRequest(deal), row);
});

test("actual rating and score override display assumptions", () => {
  const row = dossierRequest({ ...deal, exposure: 0, rating: "AA", compliance_score: 95,
    collateral_coverage: 140, pricing: "Repo + 285 bps" });
  assert.equal(row.exposure, 0);
  assert.equal(row.rating, "AA");
  assert.equal(row.compliance_score, 95);
  assert.equal(row.recommended_pricing_bps, 285);
  assert.ok(!row.assistant.assumptions.includes("Rating"));
  assert.ok(!row.assistant.assumptions.includes("Compliance score"));
});

test("linked CPI data is reused without displaying a duplicate borrower row", () => {
  const legacy = { shared_deal_id: deal.id, borrower_name: deal.customer, credit_request_number: "CR-10241",
    exposure: 3000000, compliance_score: 90, rating: "A", collateral_coverage: 125 };
  const unrelated = { credit_request_number: "CR-10242", borrower_name: "Existing CPI Borrower", compliance_score: 70 };
  const rows = workbenchRequests([deal], [legacy, unrelated]);
  assert.equal(rows.length, 2);
  const canonical = rows.find(row => row.shared_deal_id === deal.id);
  assert.equal(canonical.rating, "A");
  assert.equal(canonical.compliance_score, 90);
  // USD historical exposure must not be relabeled as INR.
  assert.equal(canonical.exposure, 60000000);
  assert.ok(canonical.assistant.assumptions.includes("Exposure"));
});
