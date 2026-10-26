# Policy review, applicability and explanation agents

Three application agents are available in the existing backend. They are separate
from the Credit Policy Rule Extraction Agent and cannot approve, activate or
retire rules, approve exceptions, or make credit decisions.

## Where to use them

| Agent | Screen and action | Implementation |
| --- | --- | --- |
| Credit Policy Rule Quality Review Agent | Policy Intelligence → Policy Rule Library → expand a rule → **AI quality review** | Mistral structured source review |
| Credit Request Policy Applicability Agent | Compliance Review → select a credit request → **Check applicability** | Deterministic approved-condition evaluation |
| Credit Policy Compliance Explanation Agent | Compliance Review → submit an assessment → expand **Policy applicability and evaluated evidence** | Deterministic evidence template |

Credit analysts and administrators can run quality review. All authenticated users
can check applicability for requests accessible in their account. The request
selector continues to use the same combined CPI/Dossier request list as the
Credit Requests screen.

Restart the backend and reload the frontend after deploying. Quality review uses
the existing `MISTRAL_API_KEY`, `MISTRAL_POLICY_MODEL` and timeout configuration.
Applicability and explanation do not need a model call: their deterministic
implementation keeps eligibility and frozen compliance results reproducible.
These are application agents, not separately provisioned hosted agent IDs.

## Quality review

`backend/app/agents/credit_policy_rule_quality_review.py` implements the supplied
ten review dimensions: source support, atomicity, traceability, threshold fidelity,
calculation fidelity, applicability, data requirements, stage, governance and
duplication. Source text, proposals and comparison rules are untrusted data.
The agent has no tools or governance write capability.

The application loads the exact stored rule version and its registered source
clause. It supplies up to 20 comparison versions from the same policy, prioritizing
the same clause. Duplicate findings are therefore limited to those supplied
comparisons, not a claim that the entire inventory was searched.

The strict report has exactly `review_result`, `issues`, `unsupported_fields`,
`missing_fields`, `duplicate_candidates`, `recommended_revision` and `confidence`.
The only results are `ACCEPTABLE_FOR_HUMAN_REVIEW`, `REVISION_REQUIRED` and
`UNSUPPORTED`. Acceptable means ready for human review, never approved. Unknown
duplicate identifiers, extra status fields and invalid confidence are rejected.
An acceptable result containing issues or unsupported/missing fields is downgraded
to revision required. Optional null properties are not unsupported assertions.

Successful reviews record the reviewed definition snapshot and advisory report
in the existing audit history, linked to an execution log. Review findings can
be inspected under **Versions, reviews, audit and assessments**. Subsequent edits
do not alter that snapshot; rerun review against the edited version. Provider
failures return a sanitized error and do not alter rule status.

API: `POST /api/policy-rules/{rule_version_id}/quality-review` (no request body).
The response wraps the seven-field report with rule-version identity,
execution identity and `advisory_only: true`.

A [live Mistral review sample](policy-quality-review-agent-sample.json) is included.
It reviewed a stored draft and made no governance changes. AI findings remain
advisory and require human validation.

## Applicability

`backend/app/agents/credit_request_policy_applicability.py` evaluates supplied
approved and active candidates using the same three-valued condition evaluator
as the rule engine. It never calls the compliance evaluator, computes a compliance
score, evaluates evidence availability, or returns Pass/Warning/Breach.

Each decision includes candidate identity/type, `Applicable`, `Not Applicable` or
`Unable to Determine`, a reason, observed request attributes, and missing information.
AND/OR conditions retain unknown values. Missing required attributes or stage do
not imply applicability; a definite exclusion can still establish not applicable.
Rule effective-from/to dates are inclusive. Policy effective-from dates are checked
when supplied. Unknown required dates remain unresolved.

The application retrieves human-approved Active rule versions with current,
unchanged policy sources. Standalone checking includes approved Active candidates
outside their effective period so they can be shown as not applicable. Source
versions changed since approval are excluded from the operational candidate set.
Mapped policies aggregate their rule applicability: any applicable rule makes
the policy potentially applicable; otherwise unresolved rules keep it unresolved.
Explicit policy candidates can also be supplied directly to the agent.

API: `POST /api/compliance-review/applicability` with
`{"credit_request_number":"<selected request ID>"}`. It loads account-authorized
stored request data, returns an applicability report, and does not save a compliance
assessment. An empty candidate list is shown explicitly in the screen.

New full assessments also retain this independent report in their saved JSON.
The legacy finding applicability labels are preserved for historical compatibility.

## Explanation

`backend/app/agents/credit_policy_compliance_explanation.py` accepts an existing
deterministic finding. It does not recalculate inputs, formulas, thresholds,
variance or outcomes. Unknown outcomes are rejected. All six specified outcomes
are supported. Missing values are displayed as not supplied.

The strict output has exactly `short_summary`, `detailed_explanation`,
`evidence_citations`, `missing_information` and `next_required_action`. It includes
policy and rule versions, clause, applicability reason, workflow stage, observed
inputs, supplied formula/calculation description, calculated value, threshold,
operator/unit/check question, outcome, supplied variance and evidence. Contradictory
evidence is called out. Next required action is null unless an explicit approved
rule escalation/approval requirement was supplied.

The assessment pipeline saves `explanation_report` per finding, alongside the
existing `explanation` text for compatibility. The UI displays the short summary,
detailed explanation and explicitly supplied next action. Existing saved assessments
remain frozen; use the existing explicit reassessment option to produce a new
assessment with these reports.

## Contracts and verification

`GET /api/policy-agents` returns names, implementation type, versions and strict
output schemas for all three agents. Corresponding JSON Schema files are in
`backend/app/agents/*_schema.json`.

Unit tests cover governance boundaries, source-as-data prompts, output validation,
unsupplied duplicate rejection, missing evidence, missing attributes/stages,
inclusive effective dates, policy aggregation, unchanged outcomes, supplied-only
actions, missing/conflicting evidence and structured report integration.
PostgreSQL tests verify that advisory review is audited without approval or
activation and standalone applicability creates no compliance assessment. All
database fixtures are rolled back.
