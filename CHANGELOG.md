# Changelog

## Unreleased

- `cosmosproof discover` and `cosmosproof audit`: estate-wide discovery, selection and audit into `cosmosproof.audit` (DuckDB metric model) with a Parquet export.
- The scanner image is public; the Marketplace package was test-deployed with the full customer journey.
- Risk reading: unused Lakehouse Federation connections (`unused_connection`), with ingestion pipelines that use a connection excluded.
- Azure Marketplace Managed Application package (`deploy/azure/marketplace`), with certification checks as tests.
- Storage read logs (`access_logs`) as a second storage signal with exact times; `window_hours`; `grants --log-analytics`.
- Continuous monitoring: `publish:` writes runs, findings with status (new, ongoing, resolved) and run summaries; `options.auth: azure` for Databricks; config from `COSMOSPROOF_CONFIG`; Dockerfile; Container Apps Job template with Log Analytics; Databricks dashboard script.
- `lab/`: ten scenarios of fictional data in ADLS and Unity Catalog with daily producer and consumer jobs; storage-only findings warn about cache hits.
- Storage-only mode when `system.access` is not readable; storage reads count data files only; direct ADLS listing (`list_directly`, `azure` extra) with a clear error when the data role is missing; the summary distinguishes "no storage data" from "nothing unused".
- `scan` explains missing system table grants instead of failing with a stack trace; the generated onboarding says system catalog grants need a Databricks account admin (found on a real Azure tenant).
- `cosmosproof grants`: prints the onboarding grants and commands for a person to review; `databricks.list_price_discount` applies a contract discount to list prices; Parquet inventory timestamps (epoch milliseconds) are read correctly.
- Phase 2: jobs and pipelines (including Lakeflow Connect) whose outputs nobody reads, with compute cost at list price; reads by dead producers are not use; unused tables name their feeders; totals per currency.
- Phase 1: Unity Catalog and Blob Inventory readers, cross-reference engine with evidence, confidence, coverage notes and proof hash; orphan storage; PII reading; cost from the customer's rates; `scan`, `demo`, `diff` and `ledger` commands.
