<!--
Source of https://cosmosdata.ai/proof/terms. Describes accurately what is and is not offered, so
legal review starts from the facts. Not legal advice: have it reviewed before the offer goes live.
Open points for that review: the publisher's legal name; that the commercial license is granted by
the BSL licensor (today Wiliam Rosa as a person) through an offer published by Cosmos Data (assign
or license the rights to the company, or name the licensor in these terms); governing law.
-->

# CosmosProof terms of use

Last updated: 2026-11-28

## What you are getting

The CosmosProof offer on the Azure Marketplace ("the Offer") deploys CosmosProof as an Azure Managed Application into **your own Azure subscription**, and lets you install its app in your own Azure Databricks workspaces. Cosmos Data ("the Publisher") provides the deployment template, the scanner image and the app; it does not host, operate or have access to your deployment.

## License

CosmosProof is source-available under the Business Source License 1.1, published at https://github.com/WiliamRosa/cosmosproof/blob/main/LICENSE. That license allows production use only for non-commercial purposes. **An active subscription to the Offer is the commercial license** that allows your organization to use CosmosProof in production on its own data, for as long as the subscription is active. The Offer currently has one plan, **Free**: no charge and no limit on the number of workspaces, storage accounts, subscriptions or users. If paid plans are introduced later, they will be announced as described under "Changes", and existing Free subscriptions keep their license.

These terms do not reduce any right the Business Source License already gives you, including evaluation and other non-production use.

## How CosmosProof works with your data

- It only reads: it never deletes, moves or changes your data, and its only write is to the storage and Log Analytics workspace the deployment creates.
- It reads metadata (names, paths, sizes, tiers, access times, lineage), never the contents of your tables or files.
- Findings are evidence for a decision, not the decision. Every finding states what was checked, what could not be seen and a confidence level. Before you archive, move or delete anything, confirm it with the owner of the data. The Publisher is not responsible for actions you take based on a finding.
- Cost figures are estimates from public list prices and the discount you configure, not your invoice.

See the privacy policy at https://cosmosdata.ai/proof/privacy.

## Your responsibilities

- The Azure and Azure Databricks resources CosmosProof uses run in your subscription and your workspaces, and you pay their cost directly (the scheduled job, its storage and logs, the Databricks App and the SQL warehouse queries).
- You decide which read roles to grant and to which resources, and you keep your deployment's image and app up to date.
- You remain responsible for complying with the law that applies to the data in your lakehouse.

## Support and updates

Support is given by e-mail and through the contact form at https://cosmosdata.ai/proof/#contact, on business days, on a best-effort basis with no response time guarantee. New versions are announced in the GitHub repository's releases.

## Warranty and liability

CosmosProof is provided "as is", without warranty of any kind, as stated in its license. To the extent permitted by law, the Publisher's total liability under the Offer is limited to the amount you paid for the Offer in the twelve months before the claim (nothing, while the Offer is free).

## Ending the subscription

Cancelling the Marketplace subscription ends the commercial license. The resources in your subscription stay there until you delete them; deleting the Managed Application removes everything the deployment created.

## Changes

Changes to these terms or to the Offer's plans are published at this same address, with the date above updated, and do not apply retroactively.

## Contact

https://cosmosdata.ai/proof/#contact
