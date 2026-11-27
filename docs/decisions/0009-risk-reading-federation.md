# ADR 0009: Risk reading, unused Lakehouse Federation connections

- **Status:** accepted
- **Date:** 2026-11-27

## Context

The risk reading of the product promise ([ADR 0001](0001-name-scope-and-promise.md)) starts with Lakehouse Federation: a connection stores credentials to a production database, and one nobody uses is attack surface with no business value. `system.information_schema` lists connections but does not link foreign catalogs to them; the Unity Catalog REST API does.

## Decision

- Connections and foreign catalogs come from the Unity Catalog REST API (`connections`, `catalogs`), with the scan's own token. CosmosProof reads the connection type, host, owner and credential type, never the secret.
- Ingestion pipelines (Lakeflow Connect) that use a connection are listed too: such a connection is used, and the producer reading ([ADR 0005](0005-producers-and-compute-cost.md)) judges the pipeline.
- A connection is an `unused_connection` finding (risk reading, medium confidence) when it is older than the window, no pipeline uses it, and lineage shows no read of any table in its foreign catalogs inside the window. A connection with no foreign catalog is only judged when the pipeline list could be read.
- Without lineage (storage-only mode) connections are **not judged**: queries on foreign catalogs read no lake storage.
- An empty connection list is reported as "not visible", not as "no risk": the identity only sees connections it has a privilege on.

## Consequences

- Validated live with a connection to a fake host and a foreign catalog on it: the connection, its type, host, credential type and catalog are read, and the scan is unaffected by an unreachable foreign catalog.
- Not validated live: the verdict itself, which needs lineage (an account admin grant) on a workspace with real federated queries.
- The source database may serve other applications; the finding only says Databricks does not use the connection, and says so.
