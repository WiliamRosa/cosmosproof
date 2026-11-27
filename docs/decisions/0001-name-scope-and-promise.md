# ADR 0001: Name, scope and promise

- **Status:** accepted
- **Date:** 2026-11-26

## Context

Cosmos Semantic grew into a broad product that answers "what does it do?" with a list. Research into data cost tooling ([product proposal](../product-proposal.md)) found a crowded market for compute optimization and an almost empty one for stored data nobody reads on Azure: nobody cross-references ADLS files, Unity Catalog tables, query activity and database-side usage, and the closest tools admit false positives.

## Decision

**Name:** CosmosProof, published under the Cosmos Data publisher account already verified in Partner Center. It is a distinct product from Cosmos Semantic.

**Promise:** we show, with proof, what in your Azure Databricks costs money, creates risk or breaks the LGPD necessity principle without being used.

**One map, three readings:** cost (FinOps), risk (unused production credentials, load on transactional databases) and compliance (personal data at rest with no purpose in use).

**Scope:** Azure Databricks is the observation point. In order of delivery:

1. ADLS Gen2 + Unity Catalog (storage nobody reads).
2. Lakeflow Connect (CDC ingestion that feeds tables nobody reads).
3. Lakehouse Federation and database-side statistics on PostgreSQL Flexible Server and Azure SQL / SQL Server.
4. The LGPD reading over everything above.

Plain JDBC reads are a declared blind spot. Azure Data Factory, Microsoft Fabric, Power BI and Event Hubs are out of scope.

**Rules that do not bend:**

- A finding is never based on a single missing signal. Every finding carries its evidence, a confidence level and what could not be seen.
- CosmosProof never deletes, moves or changes anything. It recommends; a person acts.

## Consequences

- The pitch is one sentence and a number, not a feature list.
- Value depends on the customer running Databricks with Unity Catalog; customers without it are not a target.
- The heavily used, ungoverned side of the same map is the bridge to Cosmos Semantic, kept out of this product's pitch.
