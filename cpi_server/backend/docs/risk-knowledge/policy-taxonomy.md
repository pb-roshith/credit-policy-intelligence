# Policy classification output

The Taxonomy view now opens **Policy classification**, separate from the existing
**Spreadsheet reference dictionary**. It presents a controlled classification
dictionary, observed tree, explicit dimensions, source evidence and coverage.

`GET /api/risk-knowledge/policy-taxonomy` reads current source versions and clauses
in a consistent, read-only database transaction. `?policy_id=6` restricts the
output to one policy. Existing authentication applies. There are no database
writes, policy approvals, LLM calls or changes to executable rules on this path.

The implementation is `app/risk_knowledge/policy_taxonomy.py`. Category/topic
definitions and aliases are curated and versioned. Policy text supplies literal
occurrences, exact source evidence, dimensions and observed hierarchy branches.
This is a baseline classification proposal, not an autonomous semantic reading
or approved enterprise taxonomy. Unmatched and ambiguous content remains visible.

Observed paths follow domain → policy area → product → category → topic.
Credit risk is the configured project domain. Other dimensions require literal
evidence in the passage. Multiple products are not expanded into asserted
product-specific rules. Unknown dimensions are not inferred from filenames,
currencies, source locations or nearby passages. Topic/category co-occurrence
does not imply policy applicability or an executable requirement.

Section headings establish categories before body matches are considered. Pure
headings, page furniture, metadata and numbered control headings are retained as
source structure. Training/evaluation content has a separate content role.
Every stored current passage has a classified, structural or unclassified
disposition; this does not certify complete PDF text extraction or OCR coverage.
Synthetic labels are preserved from both catalog metadata and source wording.

The dictionary exposes definitions, inclusion/exclusion criteria, aliases,
supporting clause IDs and exact-label workbook reference candidates. Workbook
references are not approved data bindings. All classifications are PROPOSED;
existing schema/ontology approval endpoints do not approve these assignments.
Human approval and vocabulary changes require a separate governance process.

To reproduce the deliverables from the current database, run from `backend`:

```powershell
.venv/Scripts/python.exe scripts/export_policy_taxonomy.py
```

Default output is `cpi_server/backend/outputs/policy-taxonomy/` inside `cpi_server`:

- `policy-taxonomy.xlsx`: dictionary, tree, assignments, dimensions and evidence,
  complete coverage, unclassified passages and source inventory.
- `policy-taxonomy.json`: full snapshot, version and source/content digest.
- `policy-taxonomy.md`: readable tree, dictionary overview and source examples.

These snapshots are regenerated explicitly; the application view reads current
sources. Output timestamps use UTC. The original source documents and workbook
remain unchanged. Review vocabulary definitions and source assignments before
using this output as the approved basis for ontology or graph construction.
