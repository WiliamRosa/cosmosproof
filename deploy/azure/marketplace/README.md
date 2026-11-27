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
python deploy/azure/marketplace/build.py --pid <customer usage attribution GUID>
```

It compiles `mainTemplate.json` and writes `cosmosproof-managed-app.zip` (git-ignored), the file to upload in the plan's technical configuration in Partner Center. `--pid` makes the plan's attribution GUID the default of `partnerCenterPid` in the packaged template only, since the wizard does not pass it.

## The offer

| File | Content |
|---|---|
| [partner-center.md](partner-center.md) | Step by step to create the offer and its plans |
| [listing.md](listing.md) | Every listing field, ready to paste, with logos and screenshot captions |
| [pricing-proposal.md](pricing-proposal.md) | Plans and prices to decide, consistent with the license |
| [privacy-policy.md](privacy-policy.md), [terms-of-use.md](terms-of-use.md) | Sources of the pages published at cosmosdata.ai/proof/privacy and /proof/terms |
| [screenshots/](screenshots/) | 1280x720 captures of the app over a fictional bank, made by [capture.py](capture.py) |

## Before submitting

- The image `ghcr.io/wiliamrosa/cosmosproof:<version>` must be **public**: Container Apps validates it at deployment time.
- Build the package with the plan's attribution GUID (`--pid`).
- `tests/test_marketplace.py` keeps the certification rules that failed before: every TextBox has a regex (also the optional ones), defaults satisfy it, and the wizard outputs match the template parameters.
