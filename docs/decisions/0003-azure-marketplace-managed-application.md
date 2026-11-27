# ADR 0003: Delivery as an Azure Marketplace Managed Application

- **Status:** accepted
- **Date:** 2026-11-26

## Context

Banks will not send an inventory of their data estate to a third-party backend. Cosmos Semantic already went through Partner Center as a Managed Application (Cosmos Semantic ADR 0015), which fixed real template and certification problems along the way: customer usage attribution, ARM `scope` evaluation on disabled modules, and `createUiDefinition` TextBox validation (every TextBox needs a regex).

## Decision

CosmosProof ships as a second **Azure Application: Managed Application** offer under the same Cosmos Data publisher account. It runs in the customer's subscription with a managed identity, and its findings never leave the customer's tenant.

The Cosmos Semantic template is the starting point, keeping the lessons above.

**Onboarding of permissions.** A managed application only controls its own managed resource group. Reading the customer's storage and Databricks needs grants the customer gives after deployment, through a guided script:

| Grant | Purpose |
|---|---|
| Storage Blob Data Reader on each storage account (or container) | Read Blob Inventory reports |
| A Blob Inventory rule with `LastAccessTime`, `AccessTier`, `Content-Length` | File list, tier, last access |
| Last access time tracking on each storage account | Free; only records from activation onwards |
| The managed identity added to the Databricks workspace as a service principal, with `USE` and `SELECT` on the `system` schemas (`access`, `information_schema`, `lakeflow`, `billing`) and `BROWSE` on catalogs | Lineage, catalog metadata, jobs, pipelines and their cost |
| CAN USE on one SQL warehouse | Running the system table queries |

## Consequences

- No new publisher verification is needed.
- **Networking is the main gap for banks.** Storage and Databricks are usually behind private endpoints, so the app must be able to run inside the customer's virtual network. Public networking is enough for the first version; a VNet-integrated option is required before selling to a bank.
- The container image must be pullable from the customer's tenant, so the code is effectively visible. Protection comes from the license and the service, not from secrecy.
- The guided grant script is part of the product and must be tested as carefully as the code.

## 2026-11-27 update: validation on a real Azure tenant

Tested on an Azure Databricks Premium workspace with Unity Catalog and an ADLS Gen2 account, with a user-assigned managed identity standing in for CosmosProof's identity.

- **Azure part, all generated commands worked as generated:** the read-only role assignment, last access tracking (it reports a one-day granularity), the management-plane container creation and the inventory policy (read back with every field, including `hdi_isfolder`).
- **Databricks part:** `BROWSE` on a catalog works when run by the catalog owner. Every grant on the `system` catalog failed for a workspace admin: `USE CATALOG` needs `MANAGE` on `system`, and the schema grants need a **Databricks account admin**. Onboarding must therefore involve an account admin, which is a different (and usually more senior) person than the workspace admin. The generated script and the scan's error message now say so.
- **Storage paths:** Unity Catalog reports external table locations as `abfss://<container>@<account>.dfs.core.windows.net/<path>`, the same form CosmosProof builds from inventory reports, so blobs map to tables without translation.
- **SQL entitlement:** besides `CAN USE` on the warehouse, the identity's service principal needs the Databricks SQL access entitlement (`databricks-sql-access`); without it the first connection from the scheduled job failed with "This API is disabled for users without the databricks-sql-access or workspace-consume entitlements".
