# Request-based simulator

Choose a credit request in Decision Simulator. Its available-request list comes
from authoritative account-visible stored requests and Credit Dossier retrieval.
Unavailable remembered selections are cleared and replaced by the available list.
Manager-qualified native request IDs retain their account context in query,
scenario-loading and save operations. The server validates access and reads the baseline from
the stored native request or Credit Dossier; a compliance review is not required.
Scenario inputs start from the request's amount, rating, collateral coverage,
pricing and tenor when available. Missing values are explicit scenario assumptions;
ratings outside the illustrative model require a scenario rating choice.

Each new scenario stores `credit_request_number`, an immutable `request_snapshot`,
scenario inputs, changed fields, calculated results and AI recommendations in the
account-scoped `user.decision_scenarios` table. Running a scenario never updates
the original credit request. Recommendations receive the request baseline as context.

Scenario names are unique per account and credit request. The same name can be
used on another request. List and detail endpoints require the selected request
and enforce both account access and the request association. UI selections and
late responses are cleared or ignored when the request changes.

Monetary inputs and outputs use millions of the request's currency. No foreign
exchange conversion is inferred. Sensitivity points follow the actual scenario
amount, including amounts below the former USD 25 million slider floor.
The model remains illustrative; its fixed portfolio limit is 1,000 million in
the scenario currency, and model assumptions are included in results.

Earlier unlinked scenarios are retained outside active navigation. The compatibility linking API preserves original inputs/results and records that they were not derived from the new request baseline. No request association is guessed.

Endpoints:

- `GET /api/decision-scenarios/requests` lists available requests
- `GET /api/decision-scenarios/request-context?credit_request_number=...`
- `GET /api/decision-scenarios?credit_request_number=...`
- `POST /api/decision-scenarios` with request ID, name and scenario inputs
- `GET /api/decision-scenarios/{id}?credit_request_number=...`
- `GET /api/decision-scenarios/unlinked`
- `POST /api/decision-scenarios/{id}/link` with the selected request ID

The idempotent bootstrap adds request/snapshot columns and replaces the old
account-wide name index with request-specific and legacy-unlinked indexes.
