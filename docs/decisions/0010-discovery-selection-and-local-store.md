# ADR 0010: Discovery, resource selection for non-technical users, and a local store

- **Status:** proposed
- **Date:** 2026-11-27

## Context

A bank deploys CosmosProof once and its identity can reach many Azure Databricks workspaces and ADLS Gen2 accounts across resource groups and subscriptions. Some are production; many are POCs, sandboxes and development environments the customer wants left out. Adoption depends on people who are not engineers being able to see what exists, choose what to analyze and read the results, without editing YAML. With many resources, results must live in one place the customer can point Databricks or Power BI at.

## Decision

### 1. Discovery, automatic

- **Azure Resource Graph** lists, in one query across every subscription the identity can read, all `Microsoft.Databricks/workspaces` and all storage accounts with hierarchical namespace (ADLS Gen2): name, subscription, resource group, region, tags. The identity needs **Reader** on the subscriptions (or a management group) in scope.
- **Each workspace** is then asked, through its own API, for its SQL warehouses, Unity Catalog catalogs and external locations. External locations link a workspace to the ADLS accounts it uses, so storage is shown under the workspace that reads it.
- **Environment suggestion.** Each resource gets a suggested environment from its tags (`env`, `environment`, `ambiente`) or, failing that, its name (`prod`, `prd` → production; `dev`, `poc`, `sandbox`, `test`, `hml`, `qa` → non-production). Non-production resources start **unselected**. The suggestion is only a default; a person decides.

### 2. Selection, in a web UI

The product ships a small web app (Container App in the managed resource group, sign-in with Microsoft Entra ID, Portuguese and English), with three screens:

1. **What we found:** cards per workspace with an environment badge, the ADLS accounts it uses beneath it, and a switch to analyze it or not. Bulk actions: "leave out everything marked development or POC".
2. **Connections:** for each selected resource, a status in plain language (*ready*, *missing access*), and for what is missing a single consolidated script for the administrators to run, grouped by who must run it (Azure administrator, Databricks workspace administrator).
3. **Results:** totals by reading (cost, risk, PII), by resource and by owner, the findings with their evidence, and links to open the same data in a Databricks dashboard or Power BI.

The UI writes the selection to its own file in the reports storage; the scanner reads it. They never write the same file.

### 3. Scanning many resources

The scheduled job scans every selected workspace and storage account. One failing resource (missing grant, warehouse stopped, network) never stops the others: its status and error are recorded and shown on the Connections screen.

### 4. A local store: DuckDB

- The scanner keeps **`cosmosproof.duckdb`** in the reports storage: resources discovered, selections, runs, findings with status, evidence, per-resource metrics (tables, files, bytes, signal coverage) and scan events. The scanner is its only writer and uses an ETag on upload, so two runs can never overwrite each other.
- The UI reads a copy; it never writes to the database.
- After each run the store is **exported to Parquet** (`model/findings`, `model/resources`, `model/runs`, `model/resource_metrics`) in the reports storage. That is the interface for BI:
  - **Databricks:** an external location over it, views and the AI/BI dashboard (`deploy/databricks/dashboard.py`, adapted to the model).
  - **Power BI:** the Azure Data Lake Storage Gen2 connector with Entra ID sign-in over the same Parquet files, with a documented model and a starter report.

### 5. Permissions at scale

| Grant | Scope | Who |
|---|---|---|
| Reader | Subscriptions or management group in scope | Azure administrator |
| Storage Blob Data Reader | Each selected ADLS account (or its resource group) | Azure administrator |
| Service principal + SQL access entitlement + `CAN USE` on one warehouse + `BROWSE` on catalogs | Each selected workspace | Databricks workspace administrator |
| `system` schema grants (lineage, jobs, cost) | Metastore | Databricks account administrator, optional ([ADR 0006](0006-storage-only-mode.md)) |

The Connections screen generates these for exactly the selected resources.

## Consequences

- The Managed Application gains a web app and needs an Entra ID app registration for sign-in; the deployment cannot create one, so the customer's administrator creates it (a printed script) and gives its ID in the wizard.
- Reader on subscriptions is broader than today's grants; it is read-only and limited to metadata, and the scope is the customer's choice.
- The scanner becomes multi-tenant across workspaces in one customer; per-workspace tokens come from the same managed identity.
- The Marketplace offer waits for this, because selection and the Results screen are what non-technical buyers will judge.
