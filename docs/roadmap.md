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
- [x] List ADLS containers directly with Azure credentials (`list_directly`), validated on a real ADLS Gen2 account
- [x] Storage-only mode when lineage is not readable ([ADR 0006](decisions/0006-storage-only-mode.md)); data files only, `_delta_log` excluded
- [ ] Read Blob Inventory reports straight from storage instead of local files
- [ ] Join `system.query.history` as a second read signal (the SQL Query History API redacts query text, see ADR 0006)
- [ ] Validation on an Azure Databricks workspace with ADLS external tables: storage path format confirmed on Azure (2026-11-27); lineage and a real inventory report pending an account admin grant and the first daily inventory run

## Phase 2: Producers (jobs and pipelines, including Lakeflow Connect) — in progress

- [x] Jobs and pipelines whose outputs nobody reads, with their compute cost at list price ([ADR 0005](decisions/0005-producers-and-compute-cost.md)), validated against a real workspace
- [x] Reads by dead producers are not use; chains of dead producers are found to a fixed point
- [x] Unused tables name the producers that still feed them
- [x] Contract discount factor for list prices (`databricks.list_price_discount`)
- [ ] The same source table brought in several times (Lakeflow, JDBC, federation)

## Phase 3: Federation and database-side statistics

- [ ] Unused federation connections that hold production credentials
- [ ] `pg_stat_user_tables` and `sys.dm_db_index_usage_stats` to separate "nobody reads it" from "only Databricks doesn't read it"
- [ ] Ingest-or-federate recommendation from real usage

## Phase 4: Delivery

- [x] Grant script generator (`cosmosproof grants`): Databricks SQL grants, read-only Azure role, access tracking, inventory policy. Azure commands run successfully on a real ADLS Gen2 account (2026-11-27); system catalog grants need a Databricks account admin
- [ ] Managed Application template ([ADR 0003](decisions/0003-azure-marketplace-managed-application.md))
- [ ] VNet-integrated option for private endpoints
- [ ] Owner-based showback and alert delivery

## Before selling

- [ ] Real test of how federated queries and plain JDBC reads appear in lineage
- [ ] Three or four conversations with bank data leaders: which pain (cost, risk or LGPD) would they pay to solve?
- [ ] Legal review of the license
