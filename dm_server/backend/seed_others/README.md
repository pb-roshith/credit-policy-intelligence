# Deployment files

- `generated_policies/` and `policy_docs/` contain CPI policy source PDFs and DOCX files.
- `risk_schema/` contains the risk data dictionary workbook.
- `inventory_sources/` contains copies of the original bytes referenced by CPI inventory records.
- `dossier_documents/` contains the original Dossier PDFs and an index connecting them to MCP document IDs.
- `gemini.sqlite3` holds the local provider state and original document resources for Gemini.
- `outputs/` contains offline reports and exports for review.

Mount the full directory at the same path used by the [restore step](../seed_table/README.md).
CPI defaults to this directory in the workspace and accepts an absolute
`CPI_SEED_DIR` override when it is mounted elsewhere. Deploy the runtime Gemini
store separately from the static snapshot. The local provider store and CPI
inventory archive copies are excluded from Git and require private deployment storage.
