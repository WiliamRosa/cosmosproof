<!--
Source of https://cosmosdata.ai/proof/privacy. Written from the actual architecture of the offer
(ADRs 0003, 0007 and 0010), not from a template. Not legal advice: have it reviewed before the
offer goes live, in particular the publisher's legal name and the data protection obligations of
the publisher's own jurisdiction. Keep the website page and this file in sync.
-->

# CosmosProof privacy policy

Last updated: 2026-11-27

## Summary

CosmosProof, as offered on the Azure Marketplace, is an **Azure Managed Application**: everything it creates runs **inside your own Azure subscription**, and its app runs inside your own Azure Databricks workspace. Cosmos Data, the publisher, does not host, operate or have access to your deployment, the metadata it reads, or the findings it produces. There is no publisher backend that your data passes through.

## What CosmosProof reads, inside your tenant

Only with the read roles you grant to its managed identity:

- **Azure Resource Graph:** the names, resource groups, tags and locations of Azure Databricks workspaces and storage accounts in the scope you chose.
- **Unity Catalog metadata:** catalogs, schemas, tables, columns and their storage paths; and, when you grant access to the Unity Catalog system tables, lineage, query history, billing and job metadata.
- **ADLS Gen2 metadata:** file paths, sizes, access tiers and last access times, from listing, Blob Inventory reports or storage read logs in your Log Analytics workspace.

CosmosProof does **not** read the contents of your tables or files. Column names are used to recognize personal data (for example, a column called `email`); the values in those columns are never read.

## What CosmosProof writes, inside your tenant

- Its audit store (`cosmosproof.audit`), reports and run logs, in the storage account and Log Analytics workspace that the deployment creates in your subscription.
- In the app, the choice of which resources to analyze, with the e-mail address of the person who changed it, as given by your workspace's single sign-on. It is kept with that choice in a Unity Catalog volume of your workspace, so you can see who chose what.

CosmosProof never deletes, moves or changes your data.

## What Cosmos Data receives

**Does not receive:** any of the metadata, findings, reports, logs, selections or user identities above, nor any credential. The deployed code makes no call to any endpoint controlled by Cosmos Data. Its source is public at https://github.com/WiliamRosa/cosmosproof, so this can be verified.

**May receive**, through the normal Azure Marketplace flow and not through the product:

- The purchase and usage information that Microsoft shares with every Marketplace publisher (such as your subscription and tenant identifiers and the plan you chose), for billing and support.
- A customer usage attribution record, the standard Azure mechanism that tells a publisher a deployment of its offer exists. It carries no customer data.
- What you send us yourself when you contact support (an e-mail, a website form or a public GitHub issue).

The scanner image is downloaded from GitHub Container Registry when the job runs, so GitHub, not Cosmos Data, sees that download.

## Retention and deletion

Your findings and audit store stay in your subscription for as long as you keep them. Deleting the Managed Application removes every resource the deployment created. The app is removed from your workspace by a workspace administrator. Cosmos Data keeps support messages only for as long as needed to answer them.

## Contact

Questions about this policy: use the contact form at https://cosmosdata.ai/proof/#contact.

## Changes

Changes are published at this same address, with the date above updated.
