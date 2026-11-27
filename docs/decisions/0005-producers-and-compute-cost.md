# ADR 0005: Producers that feed tables nobody reads, and their compute cost

- **Status:** accepted
- **Date:** 2026-11-26

## Context

Phase 2 was planned around Lakeflow Connect, whose CDC gateway runs continuously. The system tables show that the same evidence covers every producer: `system.access.table_lineage` attributes each write to a job (`entity_metadata.job_info.job_id`) or a pipeline (`entity_metadata.dlt_pipeline_info.dlt_pipeline_id`), and `system.billing.usage` attributes compute to the same ids. Lakeflow Connect ingestion pipelines are one pipeline type among others.

A live scan surfaced the rule problems:

- A job that reads its own output (a MERGE) made that output look used.
- Excluding every self-read would flag the intermediate tables of a pipeline whose final tables *are* used.

## Decision

**Producers are jobs and pipelines.** A producer is *dead* when, inside the window, none of the tables it wrote was read by anything except itself or other dead producers. The set is computed to a fixed point, so a chain of jobs that only feed each other and end in tables nobody reads is dead as a whole.

**Reads by dead producers are not use.** Reads by live producers are, so intermediate tables of a used pipeline are never flagged.

Each dead producer becomes an `unused_producer` finding (cost reading, medium confidence, because it rests on lineage alone) with:

- the tables it wrote inside the window and the last read by anyone else;
- its usage in the window and the cost at **Databricks list price** (`system.billing.list_prices`, joined by SKU, cloud, unit and price period), normalized to a month.

List prices come from the customer's own system table, so they are not invented, but contract discounts are not applied; every such finding says so. Usage with no matching list price is reported as an understated cost.

Unused table findings also name the producers that still feed them (`fed_by`).

Deleted producers are skipped. Missing grants on `system.lakeflow` or `system.billing` become coverage notes; the storage scan still runs.

## Consequences

- Compute waste usually dwarfs storage waste: in the demo, the ingestion pipeline costs about 27 times the storage of the table it feeds.
- The grant script ([ADR 0003](0003-azure-marketplace-managed-application.md)) needs `SELECT` on `system.lakeflow` and `system.billing` as well.
- Storage and compute costs may come in different currencies (customer rates vs. list prices), so totals are reported per currency and never added across currencies.
- Detecting the same source table ingested several times (Lakeflow Connect, JDBC, federation) remains open; it needs the source connection details, not only lineage.
