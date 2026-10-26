# Credit request data and evidence layer

The pre-implementation database audit is `credit-data-rule-audit.json`. It examines latest active rule versions, input definitions, calculations, applicability, stages, sources and evidence requirements. The existing request schema supplies borrower, facility type, rating, request amount, exposure, geography, stage, collateral coverage, pricing and recommended tenor. The previous manufactured JSON financials lack entity identity, reporting periods and field-level provenance. These are the schema gaps addressed here.

`credit-data-gap-analysis.json`, `credit-data-attribute-registry.json` and `credit-data-coverage/` are generated from the connected PostgreSQL inventory and persisted account records by `python -m app.scripts.prepare_credit_data --populate`. Per-request rule details are compressed JSON exports and are ignored by Git. Counts are calculated from database records, never hardcoded. Coverage considers all active rules, independently of policy applicability; compliance continues to apply the existing policy scope gate first. Aggregate counts classify each unique rule using its highest supported category across stored demonstration requests; this is separate from a specific request's applicable compliance results.

## Storage and mapping

Shared `credit_data.credit_data_attributes` and `rule_credit_data_mappings` register every rule requirement, aliases, rule/policy IDs, source definitions, units, expected sources, evidence, applicability inputs and calculation inputs. Explicitly equivalent aliases share a canonical attribute. Ambiguous names remain in the `requirement` domain with `REQUIRES_DEFINITION`; unknown types and missing source definitions remain visible for stewardship rather than being invented. Registry synchronization retains historical mappings; API responses use current candidates.

Account-owned `"user".credit_data_records` stores normalized entity collections in versioned JSONB, protected by the existing account role and row-level security. Entities have `entity_id`, optional `period_end`, and named typed fact envelopes. Borrower, credit request, facility, exposure, financial, metric, collateral, approval and documentation attributes are sourced from actual inventory references. Additional covenant, guarantee and risk facts can use the same envelope. No separate AI or demonstration schema exists.

Multiple facilities and reporting periods are supported. Facility-dependent rules evaluate every facility separately and retain each instance; the request result uses the most severe outcome, with uncertainty preserved when no failure is confirmed. The resolution API also accepts `entity_id` and `period`. Multiple financial periods require an explicit selection rather than silently choosing one. Derived financial ratios use matching reporting-period inputs. Calendar tenor follows dates, with a fractional month for partial contractual months and month-end clamping. Currency amounts retain their currency; cross-currency conversion requires a future approved FX rule. Monetary magnitudes, years/months and percent/ratio scales are normalized deterministically.

Every stored fact includes source type, identity, value, unit, as-of date, reference/document/page/section, extraction method, confidence, extraction timestamp, model version, verification status, verifier and update timestamp. Derived provenance retains its input lineage. Synthetic values are labelled **Manufactured Demonstration Data**, with no claim of customer or bank verification. Evidence requirements remain distinct from values: manufacturing does not invent approval documents or attestations.

`facility.tenor_months` is a whole-month integer: any partial contractual month is rounded up for limit comparison. Date-age calculations can retain fractional calendar months. Business-day checks remain Unable to Assess until an approved holiday/calendar conversion is available.

## APIs and user experience

* `GET /api/credit-data/registry`: current attribute and rule mapping registry.
* `GET|PUT /api/credit-data/requests/{request_id}`: common ingestion contract; PUT requires the observed revision for existing records.
* `GET /api/credit-data/requests/{request_id}/resolve/{rule_version_id}?entity_id=...&period=...`: deterministic resolution and evaluation.
* `GET /api/credit-data/requests/{request_id}/coverage`: every current rule's available/missing fields, derived fields, sources, evidence and executability reason.
* `POST /api/credit-data/manufacture-existing`: populate missing account-owned demonstration records.
* Existing manufacturing action accepts `scenario`: compliant, boundary, near_threshold, warning, breach, multiple_breaches, missing or conflicting.

Compliance Review offers scenario selection, canonical manufacturing, coverage and actual-value provenance inspection. New assessment reviews freeze the canonical record revision, actual resolutions and evidence alongside existing rule snapshots. Historical review APIs return stored snapshots and do not recalculate with newer facts.

Scenarios manufacture inputs around the approved thresholds without changing rule definitions. One common actual value is shared by rules; incompatible policy limits can therefore prevent universal compliance. Documentary/manual rules and incomplete policy definitions remain unresolved regardless of scenario name. Missing values are never manufactured during resolution or assessment. The two demonstration remediation/monitoring documents are explicit synthetic references with manufactured text; no real approval or attestation is inferred.

Some extracted rules encode adverse predicates (for example “ICR below 2”) as success operators. The engine retains its existing contract: satisfying the approved comparison produces Pass, failing it produces its governed severity. This layer does not reverse those operators. Those definitions need separate rule stewardship before operational use.

## Future extraction architecture

Documents/system feeds → parsing/OCR → future extraction agent or connector → common fact envelopes → validation and human verification → persisted canonical record → deterministic resolution → existing policy engine.

The extraction agent is not implemented or simulated. MANUAL, DOCUMENT_EXTRACTED and BANK_SYSTEM producers submit the same PUT contract, supply source identities and evidence references, and use optimistic revision checks. AI confidence is metadata, not evidence of approval. Unsupported types, contradictory sources, missing documents and freshness gaps require review. Rules can specify `data_freshness_days`; undefined freshness limits are not invented. No model generates actual values in the assessment path.
