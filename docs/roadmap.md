# Roadmap

Phases follow [ADR 0001](decisions/0001-name-scope-and-promise.md).

## Phase 1: ADLS Gen2 + Unity Catalog — in progress

- [x] Unity Catalog reader: tables, columns, last read and write per table and path (`system.information_schema`, `system.access.table_lineage`), validated against a real workspace
- [x] Blob Inventory reader (CSV and Parquet)
- [x] Cross-reference engine with evidence, confidence, coverage notes and proof hash
- [x] Storage nobody owns (orphan paths)
- [x] LGPD reading: unused tables holding personal data (column names, from Cosmos Semantic)
- [x] Cost estimate from the customer's own rates per tier
- [x] `diff` between runs and the realized-savings ledger
- [ ] Read Blob Inventory reports straight from storage (managed identity) instead of local files
- [ ] Join `system.query.history` as a second read signal
- [ ] Validation on an Azure Databricks workspace with ADLS external tables

## Phase 2: Lakeflow Connect

- [ ] Ingestion pipelines whose target tables nobody reads, with the gateway compute cost
- [ ] The same source table brought in several times (Lakeflow, JDBC, federation)

## Phase 3: Federation and database-side statistics

- [ ] Unused federation connections that hold production credentials
- [ ] `pg_stat_user_tables` and `sys.dm_db_index_usage_stats` to separate "nobody reads it" from "only Databricks doesn't read it"
- [ ] Ingest-or-federate recommendation from real usage

## Phase 4: Delivery

- [ ] Managed Application template and guided grant script ([ADR 0003](decisions/0003-azure-marketplace-managed-application.md))
- [ ] VNet-integrated option for private endpoints
- [ ] Owner-based showback and alert delivery

## Before selling

- [ ] Real test of how federated queries and plain JDBC reads appear in lineage
- [ ] Three or four conversations with bank data leaders: which pain (cost, risk or LGPD) would they pay to solve?
- [ ] Legal review of the license
