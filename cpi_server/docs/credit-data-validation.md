# Credit data validation — 14 October 2026

Implemented and verified in the existing PostgreSQL/FastAPI/React application.

* Backend suite with `RUN_CREDIT_DATA_DB_TESTS=1`: 147 tests run, 132 passed, 15 existing inventory integration tests skipped.
* 17 canonical data tests cover dates, tenor comparisons, unit conversion, ratios, missing and contradictory facts, exact boundaries, multiple facilities, reporting periods, provenance, manufactured identity, mapping and immutable resolution snapshots.
* Two rollback-only PostgreSQL tests use an unchanged rule from the connected inventory. The end-to-end path manufactures canonical facts, persists them, resolves actual tenor, executes the deterministic rule, persists the review and provenance, then changes current facts and verifies that the saved review remains unchanged. The other verifies account isolation and optimistic revisions.
* Frontend production build passed; all seven existing frontend tests passed.

The optional older suite with `RUN_INVENTORY_DB_TESTS=1` was also run: 11 tests fail against existing inventory behavior (four assertion failures and seven errors). Its draft/submit/activate expectations conflict with the application's existing rules-available-by-default implementation and removed lifecycle actions. This layer does not reinstate that retired workflow. These failures remain separate from the passing credit-data database tests.

The cached-review unit test was updated to match the current run endpoint: a new assessment gets a new review ID and the historical snapshot is retained.

No Mistral arithmetic or actual-value generation runs in resolution. Policy applicability and advisory explanations retain the application's existing model-backed services; those services were stubbed in the rollback-only deterministic end-to-end test to isolate data storage and assessment behavior.

The future extraction agent and bank connectors are interface designs, not deployed integrations. Registry metadata gaps and incomplete/adverse-predicate rule definitions remain explicit stewardship work. Production browser interaction was not automated; the UI was validated by the production build.
