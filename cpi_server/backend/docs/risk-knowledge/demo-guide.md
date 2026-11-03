# Selected policy to policy intelligence

1. Start the existing CPI backend/frontend and sign in.
2. Open Policy Intelligence > Policy Rule Library.
3. Choose a policy in the Policy dropdown. For a batch, leave the dropdown on All policies, expand the document list and explicitly check the desired policies.
4. Click Extract Rules. There is no need to open Risk Knowledge or build a graph manually first.
5. Follow the progress stages: risk schema, taxonomy proposals, source ingestion, clause classification, ontology discovery, rule extraction, taxonomy mapping, validation and knowledge graph.
6. Open a resulting rule. Compare its exact source clause, classifications, original/normalized terms, approved ontology links and validation checks. Unresolved mappings stay visible for review.
7. New pipeline results are drafts. Review source wording and operational input mappings, edit if necessary, submit and approve in the same details dialog. Submission refreshes knowledge evidence for an edited version.
8. Activate a reviewed version explicitly. If an older version is active, record a rationale and deactivate that predecessor first. Existing active legacy rules are retained while a replacement is still a draft.
9. Click View in knowledge graph to open the focused NetworkX evidence path in Risk Knowledge.
10. Continue with the existing Credit Requests and Compliance Review workflows for deterministic assessment.

Only the selected documents are processed. Existing inventory extraction URLs dispatch to the same pipeline. Numeric rule validation, bounded model retries and per-batch checkpoints remain in place. A failed step is visible; valid persisted drafts can be recovered on retry.

The existing Mistral extraction credential is required for real policy-rule extraction. Auxiliary knowledge tasks can run in local mock mode. No synthetic policies, borrowers or approvals are seeded. Unapproved vocabulary or inferred ontology relationships are never silently promoted to approved facts.
