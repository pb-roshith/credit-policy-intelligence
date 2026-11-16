# Current policy knowledge workflow

The active workflow is **taxonomy -> ontology -> AI rule extraction -> semantic knowledge graph -> graph-based compliance assessment**. All policy tabs use current source versions and the same semantic rule identifiers.

- **Source Assets** lists the registered policy corpus and the spreadsheet reference dictionary.
- **Taxonomy** displays the source-backed policy classification tree. The spreadsheet dictionary is read-only reference material.
- **Ontology** exposes the current 1.2.0 semantic schema, JSON Schema, OWL and SHACL.
- **Policy Evidence** displays every current source passage, extracted requirements and scope review.
- **Policy Rule Library** displays current semantic extractions with quantitative/qualitative and review-state filters. Proposed rules remain separate from published graph rules.
- **Knowledge graph** starts small. Policy nodes reveal rules; rule nodes reveal source-backed products, segments, conditions, metrics, thresholds, exceptions and approvals. At most six neighbors are drawn at a time, with navigation for the complete neighborhood.
- **Policy controls** provides a published qualitative-requirements view and a separate manufactured-control register. Data Manufacturing can generate demonstration ownership, frequency, testing and effectiveness values; these are labelled manufactured and do not become extracted policy facts.
- **Compliance Review** traverses current graph relationships using request facts. AI explains retrieved evidence; it does not select applicable rules or determine outcomes. Missing scope and evidence remain unresolved.
- **Requests, Dashboard and Portfolio** exclude scores from earlier assessment methods. Explicitly labelled newly manufactured exceptions are available for workflow testing. Requests without a current assessment show Not assessed. Incomplete assessments have no fabricated score.
- **Simulator** stores scenarios against the selected authorized credit request. Its financial calculations are scenario models, not additional policy rules or compliance approvals. Older unlinked scenarios remain stored outside the active selector.

Current extraction pipeline: `policy-semantic-llm-v1`. Semantic records are shared JSONB metadata of kind `semantic_policy` in the existing policy store. Published graph instances are assembled from validated approved rules and current source snapshots. Source/checksum and knowledge fingerprints prevent old versions being presented as current.

Policy Copilot retrieves current published rules and their graph neighborhood. Citations are checked against the retrieved rule IDs and display exact stored source quotations. Earlier remote-library conversations are not reused.

Reviewer identity comes from authentication. Human rule/scope corrections retain audit history and invalidate outdated assessments. Demonstration request facts remain clearly labelled; they do not alter extracted policy requirements.

See [finalization and validation](../finalization.md), [AI extraction cycle](ai-knowledge-cycle.md), [policy taxonomy](policy-taxonomy.md), and [business semantic model](business-semantic-model.md).

## Validation and exports

From `cpi_server/backend`:

```powershell
.venv/Scripts/python.exe scripts/export_policy_taxonomy.py
.venv/Scripts/python.exe scripts/export_semantic_model.py
.venv/Scripts/python.exe scripts/export_connected_knowledge.py
.venv/Scripts/python.exe scripts/validate_current_solution.py
```

These commands read existing extraction results and do not call AI. The current deliverables live under `cpi_server/outputs/policy-taxonomy`, `cpi_server/outputs/ontology`, `cpi_server/outputs/extracted-knowledge`, and `cpi_server/outputs/finalization`. Superseded examples, checkpoints and schema packages are preserved under `cpi_server/outputs/archive`.

Run the existing frontend on port 5173 and backend on port 8002 using `cpi_server/run.md`. No new frontend dependency was added.
