# ADR 0006: Storage-only mode when lineage is not readable

- **Status:** accepted
- **Date:** 2026-11-27

## Context

On a real Azure tenant, grants on `system.access`, `system.billing` and `system.lakeflow` need a Databricks **account admin**; workspace and metastore admins get `PERMISSION_DENIED` ([ADR 0003](0003-azure-marketplace-managed-application.md)). Many banks will not grant that to a new tool on day one. `system.information_schema` stays readable with `BROWSE`.

Two fallbacks were tried:

- **SQL Query History API** (`/api/2.0/sql/history/queries`): available to a workspace admin, but the workspace returned every `query_text` as `<REDACTED>`, so tables cannot be parsed from it. Not reliable enough to build on.
- **ADLS itself.** Every reader of a table, whether a Databricks job, a notebook, plain JDBC through Databricks, or a tool outside Databricks reading the files, ends up reading files in the lake, and last access tracking records it. It also covers the JDBC blind spot of lineage.

## Decision

When lineage cannot be read, the scan runs in **storage-only mode** instead of failing:

- Tables, owners, storage paths and columns still come from `system.information_schema`.
- A table or orphan path is a finding only when storage last access covers the whole window and shows no read. Without that evidence it is not judged.
- No storage-only finding is above **medium** confidence; high needs lineage and storage to agree.
- Jobs and pipelines are not analyzed (they need lineage and billing); the report says so.

Storage evidence counts **data files only**. Delta writers also read `_delta_log`, so log files would make a table that is only written look read. The trade-off, stated on every Delta finding, is that a query answered from Delta statistics alone (for example `COUNT(*)`) touches no data file.

Storage can now be **listed directly** (`list_directly: true`, `azure` extra, Storage Blob Data Reader) instead of waiting for the first Blob Inventory report. Owner or Contributor alone do not give access to data; the scan says so when listing is denied.

## Consequences

- Onboarding can start with only Storage Blob Data Reader and `BROWSE`, and add the account admin grants later for lineage, jobs and cost.
- The window must be longer than last access tracking granularity (one day), otherwise a daily reader can look silent.
- Queries answered by the Databricks SQL result cache or the disk cache read no storage, so a table that is only ever queried that way looks unused; storage-only findings say so. Lineage does not have this blind spot.
- Listing is fine for small and medium lakes; inventory reports remain the choice for large ones.
- Validated live: listing returns size, tier, last modified and last access for an ADLS Gen2 account, and Unity Catalog managed tables live under `managed/__unitystorage/...`, which maps through their storage path like external tables.
