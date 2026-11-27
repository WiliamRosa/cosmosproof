# Marketplace listing content

Copy for the Partner Center offer's "Offer listing" page. It describes only what is implemented and validated in this repository (see the [README](../../../README.md), the [roadmap](../../../docs/roadmap.md) and ADRs [0003](../../../docs/decisions/0003-azure-marketplace-managed-application.md) and [0010](../../../docs/decisions/0010-discovery-selection-and-local-store.md)). Paste each field as is; the step-by-step is in [partner-center.md](partner-center.md).

Wording rules: say **Lakehouse FinOps** (never "LakeOps", a different vendor), **PII** (not a specific country's law) and **source-available** (never "open source").

## Offer name

CosmosProof

## Search results summary (max 100 characters)

Lakehouse FinOps for Azure Databricks: find unused data that costs money or holds PII, with proof.

(98 characters)

## Short description (max 256 characters, shown on the offer card)

CosmosProof finds what in your Azure Databricks lakehouse costs money, creates risk or holds PII without being used. Every finding comes with its evidence, a confidence level and a proof hash. Read-only, runs in your subscription.

## Description (long, HTML allowed in Partner Center; plain paragraphs below)

Most data lakes keep paying for data nobody reads. Tables that were loaded once for a project that ended, copies of production kept "just in case", pipelines still feeding tables no report uses, and personal data stored with no purpose in use. Nobody deletes them, because nobody can prove they are unused.

CosmosProof is a Lakehouse FinOps product for Azure Databricks and ADLS Gen2 that gives you that proof. It crosses Unity Catalog lineage with storage activity in ADLS Gen2 and only calls something unused when the evidence agrees. Each finding shows what was checked, what was found, what could not be seen, and a confidence level, sealed with a proof hash so the same finding can be verified later.

**One map, three readings**

- **Cost:** tables and files nobody reads, sized from storage, with an estimated monthly cost and the cheaper storage tier they could move to. With Unity Catalog system tables, also the jobs and pipelines that keep feeding tables nobody reads, with their compute cost.
- **Risk:** production credentials and federated connections that exist with no real use.
- **PII:** personal data (such as tax IDs, e-mails and names) stored in tables nobody reads, the data that is hardest to justify keeping.

**Built for a whole estate, not one workspace**

- Discovers every Azure Databricks workspace and ADLS Gen2 account in the subscriptions or management group you choose, through Azure Resource Graph.
- Suggests an environment from tags and names and leaves development and POC resources out by default; people choose what to analyze.
- Keeps every run in its own audit store (`cosmosproof.audit`): resources, runs, findings, per-resource health and trend, ready for Power BI or a Databricks dashboard if you want one.

**An app for the people who decide**

CosmosProof includes a Databricks App, in English and Portuguese, for people who are not engineers. They sign in with the workspace's existing single sign-on: no app registration, no new user database. It shows the open findings, the estimated monthly cost, the unused storage, the PII at rest and the trend run after run, with each finding's evidence one click away. Findings that are resolved show up as resolved; resources the last run could not read are reported as unverified, never as resolved.

**Read-only and inside your tenant**

CosmosProof never deletes, moves or changes your data. It runs as a managed identity in your own subscription with read roles that you grant, and writes only to its own reports container. Nothing is sent to the publisher. The source code is public (source-available under the Business Source License 1.1), so your security team can read exactly what it does.

**What this offer deploys**

A Managed Application in your subscription: a user-assigned managed identity, a scheduled Azure Container Apps Job that runs the audit daily, a storage account for the reports, and a Log Analytics workspace for the run logs. After deployment, you grant the identity read access and a workspace administrator installs the app; the deployment outputs list the exact steps.

## Search keywords (max 3)

- Lakehouse FinOps
- Azure Databricks
- unused data

## Categories

- Analytics
- IT & Management Tools (or Security, if Partner Center allows only one more: compliance reading)

## Industries (optional)

- Financial Services (banking and insurance: the first target customers)

## Useful links

- Product page: https://cosmosdata.ai/proof/
- Documentation and source (source-available, BSL 1.1): https://github.com/WiliamRosa/cosmosproof
- How confidence works: https://github.com/WiliamRosa/cosmosproof/blob/main/docs/decisions/0004-evidence-and-confidence-model.md
- Lab with every scenario, for a trial on your own workspace: https://github.com/WiliamRosa/cosmosproof/tree/main/lab

## Support contact

- Website contact form: https://cosmosdata.ai/proof/#contact
- Public issues: https://github.com/WiliamRosa/cosmosproof/issues
- Support e-mail: fill in Partner Center with the same address used for the Cosmos Semantic offer.

## Privacy policy URL

https://cosmosdata.ai/proof/privacy (source: [privacy-policy.md](privacy-policy.md))

## Terms of use URL

https://cosmosdata.ai/proof/terms (source: [terms-of-use.md](terms-of-use.md))

## Logos

- Small (48x48): [`brand/png/cosmosproof-icon-48.png`](../../../brand/png/cosmosproof-icon-48.png)
- Large (216x216): [`brand/png/cosmosproof-icon-216.png`](../../../brand/png/cosmosproof-icon-216.png)

## Screenshots (1280x720 PNG)

Captured by [`capture.py`](capture.py) from the real app over a fictional bank (no customer data). Captions to paste:

1. `screenshots/01-overview.png`: Open findings, monthly cost, unused storage, PII at rest and risks across the whole estate.
2. `screenshots/02-findings-evidence.png`: Every finding with its recommendation, the evidence behind it, what could not be seen and a proof hash.
3. `screenshots/03-overview-dark.png`: Dark mode, in English or Portuguese, for the people who decide.
4. `screenshots/04-resources.png`: Every workspace and ADLS account discovered; development and POC start unselected.
5. `screenshots/05-connections.png`: What is ready and what lacks access, with one script for the administrators.

## Video (optional)

Not created yet. Same style as the Cosmos Semantic video: dark mode, captions, narration; from the Marketplace wizard to the first findings in the app.

## Portuguese summary (for the website and LinkedIn, not for Partner Center)

**CosmosProof: Lakehouse FinOps para Azure Databricks.** Mostramos, com prova, o que no seu Azure Databricks custa dinheiro, gera risco ou guarda PII sem ser usado. O CosmosProof cruza a linhagem do Unity Catalog com a atividade de leitura no ADLS Gen2 e só chama algo de não usado quando as evidências concordam. Cada achado traz as evidências, o que não pôde ser visto, um nível de confiança e um hash de prova. Somente leitura, roda na sua assinatura, nada sai do seu tenant.
