# Credit Policy Rule Extraction Agent

The application agent is `CreditPolicyRuleExtractionAgent` in
`backend/app/agents/credit_policy_rule_extraction.py`. Its versioned instructions
are `credit_policy_rule_extraction_prompt.txt`; its public JSON Schema is
`credit_policy_rule_extraction_schema.json`, generated from the strict Pydantic
contract in `services/credit_policy_extraction_schema.py`.

The agent uses the existing server-side Mistral configuration and `chat.parse`.
It has no tools, performs no assessment arithmetic, and cannot approve or activate
rules. Policy/run identity metadata is supplied by the application independently
of untrusted document content. Provider retries are disabled in the SDK; the
existing extraction workflow applies bounded, logged application retries.

The output envelope preserves policy_id, policy_version, source_document_id,
extraction_run_id, rules, non_rule_content and processing_warnings. Each rule uses
the requested uppercase category/operator/threshold/risk-severity enums and retains
input definitions/units, evidence, conditions, stages, ambiguity and review flags.
Unknown pages and mandatory flags are null rather than invented zero/true values.
Every proposal is DRAFT and requires_human_review=true.

Exact quotes and source references are verified against the supplied registered
spans. Whitespace-only wrapping is restored to the original excerpt. Authoritative
registered section/page metadata overrides model formatting differences. Numeric
thresholds must occur in the supporting excerpt. Unsupported claimed data sources,
evidence, severity and authorities are unresolved, with processing warnings.
Definition/guidance/background/example entries are retained separately from rules.

Risk severity CRITICAL/HIGH/MEDIUM/LOW is preserved as `risk_severity` in the
inventory, separately from the operational failed-check outcome WARNING/BREACH.
Business reviewers must configure the latter; it is never inferred from risk rank.
The captured formula remains `source_calculation_logic`. Only a direct declared
field, a declared-field ratio or its explicit percentage form can be translated
into the existing safe calculation data model. Other formulas require manual
mapping. No formula string is executed as code. Ambiguous applicability cannot
default to all requests.

Use Policy Intelligence → Policy Rule Library → Extract selected policy.
Administrator bulk generation uses the same agent. After generation, select the
policy and choose Agent extraction reports to inspect the exact structured output,
including non-rule content and processing warnings. Existing completed extractions
and approved versions are preserved; they are not silently regenerated. Select a
source clause and use Preview agent proposals to run the new contract explicitly
without replacing existing inventory versions.

APIs:

- GET `/api/policy-rule-agent`: name, model, prompt version and public output schema.
- POST `/api/policies/{policy_id}/propose-rules`: existing analyst/admin background action.
- POST `/api/inventory/generate`: existing admin bulk action.
- POST `/api/policies/{policy_id}/rule-extraction-preview` with clause_ids: explicit report-only extraction.
- GET `/api/policies/{policy_id}/extraction-reports`: validated contract reports.

Validated reports are stored in `credit_data.policy_extraction_reports`, linked to
agent execution, source document and policy version. They contain business outputs,
not hidden model reasoning. The repeatable bootstrap migration adds this table and
input-field definition/unit columns. Restart the backend to load the new agent.
Existing approvals and activation controls remain separate.

Programmatic usage from backend:

```python
from uuid import uuid4
from app.agents.credit_policy_rule_extraction import CreditPolicyRuleExtractionAgent
from app.services.policy_ingestion import ingest_policy
from app.services.rule_extraction import clause_batches

policy, version, document, clauses = ingest_policy(policy_id)
agent = CreditPolicyRuleExtractionAgent()
for batch in clause_batches(clauses):
    report = agent.run(
        policy_id=policy["policy_id"],
        policy_version=version["version"],
        source_document_id=document["id"],
        extraction_run_id=str(uuid4()),
        clauses=batch,
    )
    print(report.model_dump_json())
```

Use the existing background workflow for durable run logging, reports and Draft
inventory persistence; programmatic `agent.run` returns proposals without changing
rule lifecycle state.

The injected-document tests check that source commands stay in the source message,
that the agent has no tools, that fabricated evidence/thresholds are rejected or
unresolved, and that status/review overrides cannot pass validation. Human review
is still essential for semantic interpretation of supported source material.

A live Mistral call produced a validated DRAFT proposal using the new contract. See [actual sample output](credit-policy-extraction-agent-sample.json).
