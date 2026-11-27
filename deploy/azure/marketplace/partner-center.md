# Creating the offer in Partner Center

Step by step for the CosmosProof offer, under the same publisher as Cosmos Semantic (Cosmos Data). The texts to paste are in [listing.md](listing.md); the plans come from the [pricing proposal](pricing-proposal.md) once decided.

## Before starting

- [ ] The product page, privacy policy and terms are live: https://cosmosdata.ai/proof/, https://cosmosdata.ai/proof/privacy and https://cosmosdata.ai/proof/terms.
- [ ] The image `ghcr.io/wiliamrosa/cosmosproof:0.1.0` is public (Container Apps pulls it at deployment time).
- [ ] Plans and prices decided.

## 1. New offer

Marketplace offers → **+ New offer** → **Azure Application**.

- Offer ID: `cosmosproof` (permanent, appears in URLs).
- Offer alias: `CosmosProof`.

## 2. Offer setup

- Test drive: no.
- Customer leads: optional; the simplest destination is an Azure table in a storage account you own.

## 3. Properties

- Categories: see [listing.md](listing.md#categories).
- Industries: Financial Services (optional).
- Legal: **do not** use the Standard Contract; paste the link https://cosmosdata.ai/proof/terms (or the text of [terms-of-use.md](terms-of-use.md)) in the terms and conditions field. The Standard Contract does not mention the Business Source License.

## 4. Offer listing

Paste from [listing.md](listing.md): name, search results summary, short description, description, keywords, privacy policy URL, useful links, support and engineering contacts.

- Logos: `brand/png/cosmosproof-icon-48.png` (small) and `brand/png/cosmosproof-icon-216.png` (large).
- Screenshots: the five PNGs in `screenshots/`, each with its caption from [listing.md](listing.md#screenshots-1280x720-png).

## 5. Preview audience

Add the Azure subscription ID used for tests (the same one used to validate the package), so the preview can be deployed before going live.

## 6. Plans

One plan per row of the pricing table, for example plan ID `starter`, then `business` (and `evaluation` if kept public). For each plan:

1. **Plan setup:** type **Managed application**; Azure regions: Azure Global.
2. **Plan listing:** name and description; for the evaluation plan, state "non-production evaluation, up to 1 workspace, 30 days".
3. **Pricing and availability:** markets (start with Brazil and United States; add more later), price per month (and per year if offered), visibility public (or private with tenant IDs for the evaluation plan).
4. **Technical configuration:**
   - Version: `0.1.0`.
   - Customer usage attribution ID: Partner Center shows one GUID for the plan. Copy it and build the package with it:

     ```bash
     python deploy/azure/marketplace/build.py --pid <GUID>
     ```

     The zip changes only in the parameter default, so the same build can be uploaded to every plan; if each plan shows a different GUID, build once per plan before uploading.
   - Package file: `deploy/azure/marketplace/cosmosproof-managed-app.zip`.
   - Deployment mode: **Incremental**.
   - Publisher management access: **not allowed**, if the option is offered. CosmosProof is designed so the publisher never needs access to the customer's deployment. If Partner Center requires an authorization, give only the **Reader** role to a dedicated Entra group in the publisher tenant, and say so in the terms.
   - Customer actions, policies and the notification endpoint: leave empty.

## 7. Review and publish

**Review and publish** runs the certification (arm-ttk on the package, the listing rules). The rules that rejected the Cosmos Semantic package once are kept as tests in `tests/test_marketplace.py`; run `uv run pytest tests/test_marketplace.py` before every upload.

When the offer reaches **Preview**:

1. Deploy it from the preview link with the test subscription.
2. Follow the deployment outputs: give the identity Reader on the scope, and as a workspace administrator install the app (`app/deploy.py --identity-app-id <client id>`).
3. Open the app, check that the discovered resources appear, run the job once by hand (`az containerapp job start`) and check the findings.
4. Delete the test deployment, then **Go live**.

## After going live

- Add the Marketplace link to https://cosmosdata.ai/proof/ (the call to action points to the contact form until then) and to the repository README.
- New versions: build and push a new image tag, set the `image` default in `main.bicep` to it, rebuild the package with the plan's GUID and publish it as a new version of each plan.
