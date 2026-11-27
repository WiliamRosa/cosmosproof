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
| The managed identity added to the Databricks workspace as a service principal, with `USE` and `SELECT` on the `system` schemas and `BROWSE` on catalogs | Lineage and catalog metadata |
| CAN USE on one SQL warehouse | Running the system table queries |

## Consequences

- No new publisher verification is needed.
- **Networking is the main gap for banks.** Storage and Databricks are usually behind private endpoints, so the app must be able to run inside the customer's virtual network. Public networking is enough for the first version; a VNet-integrated option is required before selling to a bank.
- The container image must be pullable from the customer's tenant, so the code is effectively visible. Protection comes from the license and the service, not from secrecy.
- The guided grant script is part of the product and must be tested as carefully as the code.
