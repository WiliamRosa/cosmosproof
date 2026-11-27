# ADR 0007: Continuous monitoring

- **Status:** accepted
- **Date:** 2026-11-27

## Context

A one-off report is an audit: the customer cleans up once and stops paying. The product proposal asks for a continuous loop: alerts on new waste, an owner for each finding, and a ledger of realized savings. Monitoring could live on the Databricks side (jobs and dashboards next to the data people) or on the Azure side (where the Marketplace offer runs).

## Decision

**Run on the Azure side, show on the Databricks side, with one output contract between them.**

1. **Scheduler: an Azure Container Apps Job** runs the scanner image daily with a user-assigned managed identity. It is the same runtime the Managed Application will ship ([ADR 0003](0003-azure-marketplace-managed-application.md)), so monitoring is also the delivery prototype. The identity reaches Databricks with an Entra ID token (`options.auth: azure`) and lists ADLS directly, so the configuration holds no credential.

2. **Output contract: each run is published to a location CosmosProof owns** (`publish:`):

   ```
   runs/<run_id>/report.json      full report
   findings/<run_id>.jsonl        one row per finding, plus one per finding resolved since the
                                  previous run; status new | ongoing | resolved
   ```

   This is the only write CosmosProof makes. The identity gets Storage Blob Data Contributor **on that container only**; everywhere else it stays read-only.

3. **Dashboard: a Databricks AI/BI dashboard** reads the published rows through Unity Catalog views (`read_files` over the publish location). Data people already live in Databricks, and Unity Catalog permissions decide who sees findings, which matter because they name owners and internal assets.

Why not the alternatives:

- **A Databricks job as scheduler** needs Azure credentials inside Databricks to list ADLS (service credentials) and puts the scanner in the workspace it judges. It remains an option for customers who refuse a Container Apps resource.
- **Azure Monitor Workbooks** need the findings in Log Analytics (a data collection rule and ingestion cost) and are far from where data owners work. They stay the route for alerting into existing Azure operations (action groups), as a later step.

## Consequences

- `new` rows are the alert feed; `resolved` rows are candidates for the savings ledger.
- Every row carries the finding's proof hash, so the dashboard links to evidence that can be verified later.
- The same contract works with a local folder, for customers who run the CLI by hand.
- Container registry: the test setup uses a private Azure Container Registry with `AcrPull` for the identity; the Marketplace offer needs a publicly pullable image ([ADR 0003](0003-azure-marketplace-managed-application.md)).
