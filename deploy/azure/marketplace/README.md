# Azure Marketplace package (Managed Application)

`main.bicep` is what a customer deploys from the Marketplace into a managed resource group in their own subscription ([ADR 0003](../../../docs/decisions/0003-azure-marketplace-managed-application.md)):

| Resource | Purpose |
|---|---|
| User-assigned managed identity | The identity CosmosProof runs as; the customer grants it read access afterwards |
| Log Analytics workspace | Scanner output of every run |
| Storage account + `cosmosproof-reports` container | Published runs; the identity can write **only** there |
| Container Apps environment + Job | The daily scan |

The wizard (`createUiDefinition.json`) asks only for the discovery scope (subscriptions or a management group), the window and the schedule: workspaces and ADLS accounts are discovered, and people choose what to analyze in the app. The daily job runs `cosmosproof audit` and keeps `cosmosproof.audit` in the reports storage. The deployment outputs give the identity's IDs and the next steps: Reader on the scope, then a workspace administrator installs the app with `app/deploy.py`.

## Build

```bash
python deploy/azure/marketplace/build.py
```

It compiles `mainTemplate.json` and writes `cosmosproof-managed-app.zip` (git-ignored), the file to upload in the plan's technical configuration in Partner Center.

## Before submitting

- The image `ghcr.io/wiliamrosa/cosmosproof:<version>` must be **public**: Container Apps validates it at deployment time.
- Set `partnerCenterPid` to the customer usage attribution ID Partner Center assigns to the plan.
- `tests/test_marketplace.py` keeps the certification rules that failed before: every TextBox has a regex (also the optional ones), defaults satisfy it, and the wizard outputs match the template parameters.
