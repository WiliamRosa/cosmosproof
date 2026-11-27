# Product proposal: unused data in Azure Databricks — cost, risk and LGPD

Status: accepted on 2026-11-26 as the product's founding document. Decisions taken from it live in [docs/decisions](decisions/).

Name: **CosmosProof** ([ADR 0001](decisions/0001-name-scope-and-promise.md)). It is a separate, smaller product from Cosmos Semantic, sold under its own offer, not another feature inside it.

## 1. Central promise

> **We show, with proof, what in your Azure Databricks costs money, creates risk, or breaks the LGPD necessity principle without being used.**

One map, read three ways:

| Reading | Question it answers | Who pays attention |
|---|---|---|
| **Cost (FinOps)** | What am I paying for that nobody reads? | Data platform lead, FinOps, CFO office |
| **Risk** | Which production credentials and database loads exist with no real use? | Security, DBA, platform engineering |
| **Compliance** | Which personal data is stored with no purpose in use? | DPO, compliance, internal audit |

## 2. Why a smaller product

Cosmos Semantic does many things well, but it answers "what does it do?" with a list. This product answers with one sentence and a number. Data cost has a crowded side and an almost empty side:

- **Crowded: compute optimization.** Keebo, Espresso AI, Unravel, Select and Revefi already tune warehouses, clusters and queries, and Flexera bought Chaos Genius in January 2026. Not worth entering.
- **Almost empty: stored data nobody reads, on Azure.** Masthead flags unused tables (30 days without consumption) but is BigQuery-first and warns about false positives. Revefi offers it for Snowflake and BigQuery. Neither works at the ADLS file level. Microsoft and Databricks ship loose pieces (ADLS last access tracking, Blob Inventory, Azure Storage Discovery, Unity Catalog system tables), but nobody cross-references them. A Microsoft community responder confirmed that Fabric does not highlight orphaned or unused OneLake storage.

The gap: nobody joins **ADLS file ↔ Unity Catalog table ↔ query history ↔ database-side usage** to say "you pay for this, nobody reads it, here is the proof".

## 3. Scope

Observation point: **Azure Databricks**. Everything that lands in it or is read by it.

| Source | What "unused" means | Available evidence | Main reading |
|---|---|---|---|
| **ADLS Gen2** (external locations, volumes, external tables) | Files paid for and not read | Last access time + Blob Inventory + Unity Catalog lineage | Cost |
| **Lakeflow Connect** (CDC ingestion from SQL Server and PostgreSQL) | Ingested table nobody reads downstream | `system.access.table_lineage` + `system.query.history` on target tables | Cost (strongest case: the CDC gateway runs continuously) |
| **Lakehouse Federation** (foreign catalogs on PostgreSQL Flexible Server, Azure SQL) | Connection or foreign table nobody queries | Databricks documents that foreign-table lineage is tracked like regular Unity Catalog tables | Risk |
| **Database side** (PostgreSQL Flexible Server, Azure SQL / SQL Server) | Table nobody reads at all, not only Databricks | `pg_stat_user_tables`, `sys.dm_db_index_usage_stats` | Cost, risk |
| **Plain JDBC in notebooks** (`spark.read.jdbc`) | Not measurable | Probably invisible to lineage | Reported as a declared blind spot |

Connector maturity: Lakeflow Connect for SQL Server is GA (Azure SQL Database and Managed Instance). PostgreSQL is in Public Preview and lists Azure Database for PostgreSQL.

**Out of scope for now:** Azure Data Factory, Microsoft Fabric, Power BI/DAX, Event Hubs, schema sniffing of loose CSV/Excel/XML/JSON files.

## 4. Proof model: the real differentiator

The competitors' declared weak point is false positives. A bank will not delete or retier anything based on a guess. So every finding carries:

- **Evidence sources** that support it (e.g. "no read in `table_lineage` for 210 days; no row in `query.history`; ADLS last access 2026-03-02").
- **Confidence level**, derived from how many independent sources agree and from known coverage gaps. Lineage only records events it can infer, a minority of queries per third-party documentation, so a single missing signal never means "unused".
- **Reference date and observation window.**
- **Coverage notes** that state what could not be seen (e.g. "this table is also reachable by plain JDBC, which is not observable").

This is the same idea as the Cosmos Semantic evidence envelope (formula, rule version, hash, reference date), applied to cost and risk instead of metrics.

Two rules follow from it:
1. **"Unused by Databricks" is not "unused".** PostgreSQL and SQL Server serve other applications. Database-side statistics separate "nobody reads it" from "only Databricks doesn't read it". The SQL Server DMV resets on restart, which must be shown as a coverage note.
2. **The product never deletes anything automatically.** It recommends, with evidence. A human acts.

## 5. The three readings in detail

### 5.1 Cost (FinOps)

- **Dead storage in ADLS:** paths and external tables with no reads in the window, with monthly cost per tier.
- **Dead ingestion:** Lakeflow Connect pipelines whose target tables nobody reads. The gateway compute is paid every day.
- **Data paid for several times:** the same source table brought in by Lakeflow Connect, read by JDBC in a notebook, and exposed through federation. Detected by matching host, database and table of each connection. "You pay three times to bring the same table" is a message nobody else is delivering.
- **Tier recommendations** that respect minimum retention penalties (90 days in cold).
- **To validate:** Databricks predictive optimization only maintains Unity Catalog *managed* tables. Banks often have many *external* Delta tables in ADLS with history and snapshots nobody vacuums. If confirmed, this is extra recoverable storage.

### 5.2 Risk

- **Unused federation connections** that still hold production credentials. This is attack surface with no business value.
- **Ingest vs federate, based on real usage:**
  - A federated table queried all the time is hammering the transactional database and should be ingested.
  - An ingested table read once a month is paying for a continuous CDC gateway and should be federated.

  This optimizes cost and operational risk at the same time, and it is specific to the Databricks ecosystem.

### 5.3 Compliance (LGPD)

- **Personal data at rest with no purpose in use.** The LGPD necessity principle makes personal data kept without an active purpose a liability, not just a cost.
- Cosmos already detects sensitive columns by regex (`cosmos bootstrap`, LGPD sensitivity flags). Crossing "contains CPF" with "nobody read it in 180 days" turns a FinOps report into a compliance report. In a bank, compliance has its own budget, often easier to approve than cost tooling.

## 6. Recurring value: the continuous loop

Without this it is a one-time audit: the customer runs it once, cleans up, and has no reason to keep paying.

1. **New-waste alerts.** Example: "this Lakeflow pipeline created 30 days ago feeds a table nobody has read." Waste is caught when it appears, not a year later.
2. **Owner of the waste.** Use Unity Catalog owners and tags to attribute cost, risk and compliance findings to a team. This enables showback or chargeback and makes someone accountable.
3. **Realized-savings ledger.** Every action taken is recorded with its evidence and the amount saved or risk removed. It proves the return over time and opens the option to charge a share of savings.

## 7. Delivery and architecture (high level)

- **Azure Marketplace Managed Application**, the same model just published for Cosmos Semantic. It runs in the customer's subscription, with the customer's managed identity and the roles they choose. Data inventory never leaves their tenant, which is a trust argument as strong as the feature itself for a bank.
- **Reuse from Cosmos:** PostgreSQL and SQL Server connectors, LGPD sensitivity detection, evidence model, console patterns, deployment template.
- **New:** outbound Azure authentication (managed identity), readers for Unity Catalog system tables and Blob Inventory, the cross-reference engine, the alert loop and the savings ledger.

Permissions the customer grants:

| Access | Why |
|---|---|
| `USE` and `SELECT` on Databricks system schemas | Lineage and query history |
| Storage Blob Data Reader + a Blob Inventory rule | File list, tiers, last access |
| Last access time tracking enabled on the storage account | Free; only records from activation onwards |
| SQL login with usage-statistics permission on each database | Database-side usage (must be explicit in onboarding) |

**Value on day one:** ADLS last access only starts counting once enabled, but Unity Catalog system tables already hold about one year of history. The first report relies on that past; precision grows over time.

## 8. Competitors

| Player | What it does | Where it falls short for this case |
|---|---|---|
| Masthead | Unused tables by consumption | BigQuery-first; admits false positives from unseen tools |
| Revefi | Stale and unused tables, cost | Unused-table feature shown for Snowflake/BigQuery, not Databricks |
| Keebo, Espresso AI, Unravel, Select, Chaos Genius (Flexera) | Compute optimization | Different problem |
| LakeOps | Orphan files and snapshots in Iceberg | Technical garbage, not usage-based; Iceberg-focused |
| Azure Storage Discovery | Capacity insights | Capacity, not usage by pipeline. **Main native threat** |
| Databricks predictive optimization | Maintenance of managed tables | Managed tables only, no usage verdict |

## 9. Risks

- Microsoft may extend Azure Storage Discovery in this direction. Defense: cross-service proof, which a storage-only product cannot do.
- Full value depends on the customer having Databricks with Unity Catalog.
- Lineage coverage is partial: federation and JDBC behavior must be confirmed in a real workspace before any promise.
- Database-side statistics require SQL credentials, a trust hurdle in banks.
- Competitor information comes mostly from vendor material and secondary sources.

## 10. Phases

1. **ADLS + Unity Catalog.** The storage case, with immediate value from system-table history.
2. **Lakeflow Connect.** The wasted-compute case, the strongest money argument.
3. **Federation + database-side statistics.** Risk and ingest-vs-federate recommendations.
4. **LGPD reading.** Crossing sensitivity detection with usage.
5. **Continuous loop** (alerts, owners, savings ledger) built in from phase 1 for the cost reading, extended to the others as they arrive.

JDBC stays a declared blind spot in every phase.

## 11. Before building: two cheap validations

1. **Real test in the Databricks workspace** to confirm how federated queries (PostgreSQL, SQL Server) and plain JDBC reads appear in `system.access.table_lineage` and `system.query.history`.
2. **Three or four conversations with bank data leaders** (natural access through the São Paulo Databricks User Group) with one question: *which of the three pains (cost, risk or LGPD) would you pay to solve?* The answer decides which reading leads the pitch.

## 12. Later, not now

The other side of the same map, heavily used tables with no owner, description or certification, is the natural bridge to Cosmos Semantic. It stays out of this product's pitch and becomes an expansion path once the core is proven.

## References

- [Azure Databricks: lineage system tables](https://learn.microsoft.com/en-us/azure/databricks/admin/system-tables/lineage)
- [Azure Databricks: foreign catalogs](https://learn.microsoft.com/en-us/azure/databricks/query-federation/foreign-catalogs)
- [Azure Databricks: data lineage](https://learn.microsoft.com/en-in/azure/databricks/data-governance/unity-catalog/data-lineage)
- [Lakeflow Connect SQL Server](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/sql-server-pipeline)
- [Lakeflow Connect PostgreSQL](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/postgresql-pipeline)
- [Databricks predictive optimization](https://docs.databricks.com/en/optimizations/predictive-optimization.html)
- [ADLS Gen2 access-time lifecycle GA](https://mc.merill.net/message/AZ-access-time-based-lifecycle-management-adls-gen2)
- [Azure Blob inventory](https://learn.microsoft.com/en-us/azure/storage/blobs/blob-inventory)
- [Azure access tiers](https://learn.microsoft.com/en-us/azure/storage/blobs/access-tiers-overview)
- [Azure Storage Discovery capacity insights](https://techcommunity.microsoft.com/blog/azurestorageblog/azure-storage-discovery-now-offers-advanced-capacity-insights/4563651)
- [Fabric community: OneLake unused storage](https://community.fabric.microsoft.com/t5/Fabric-platform/metric-details-for-onelake-storage/m-p/4902057)
- [DataHub Databricks source docs](https://docs.datahub.com/docs/generated/ingestion/sources/databricks)
- [Atlan: track lineage for Databricks jobs](https://atlan.com/know/databricks/how-to-track-lineage-databricks-jobs/)
- [Masthead storage costs](https://docs.mastheadata.com/cost-insights/storage-costs)
- [Masthead insights](https://docs.mastheadata.com/developer/api/insights)
- [Revefi solutions](https://www.revefi.com/solutions)
- [FinOps X 2026 sponsors analysis](https://finopsweekly.com/blog/what-57-finops-x-sponsors-reveal-about-the-finops-market-in-2026/)
- [Flexera (Chaos Genius acquisition)](https://en.wikipedia.org/wiki/Flexera)
- [LakeOps Iceberg FinOps 2026](https://lakeops.dev/blog/state-of-iceberg-finops-cost-reduction)
