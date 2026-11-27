# ADR 0002: Separate repository, Business Source License and dependency on Cosmos Semantic

- **Status:** accepted
- **Date:** 2026-11-26

## Context

CosmosProof needs code Cosmos Semantic already has: the PostgreSQL, SQL Server and Databricks connectors, PII detection by column name, and the configuration conventions. Cosmos Semantic ADR 0005 says commercial code lives in a separate repository that depends on the core like any other user. The Cosmos Semantic repository is public and runs an agent routine that opens and merges pull requests by itself.

The maintainer asked for a public repository with a license "open like Cosmos", but one that does not allow commercial use without permission.

## Decision

**Repository:** `WiliamRosa/cosmosproof`, public, separate from `cosmos-semantic-platform`.

**Dependency:** CosmosProof installs `cosmos-semantic` from PyPI (`>=0.5,<0.6`) and imports from it. Anything both products need is added to Cosmos Semantic through a normal pull request there; CosmosProof only consumes released versions.

**License:** Business Source License 1.1, not Apache 2.0.

| Parameter | Value |
|---|---|
| Licensor | Wiliam Rosa |
| Additional Use Grant | Production use for non-commercial purposes only (personal, academic, non-profit) |
| Change Date | 2030-11-26 (or four years after each version's first release, whichever comes first) |
| Change License | Apache License 2.0 |

Anyone may read, copy, modify and use the code in non-production settings, so a bank can evaluate it freely. Production use by a company requires a commercial license, which the Azure Marketplace offer provides. Each version becomes Apache 2.0 after four years.

Alternatives considered:

- **Apache 2.0 (like Cosmos Semantic):** allows any company to run it commercially for free. Rejected by the maintainer's requirement.
- **PolyForm Noncommercial:** forbids commercial use entirely, including a company's evaluation, and never converts to open source. Too strict for a product sold to companies that must try it first.
- **Elastic License 2.0:** only forbids offering it as a managed service; a bank could use it in production for free. Does not meet the requirement.

## Consequences

- BSL is **source-available, not open source** (not OSI-approved). Public material must say "source-available", never "open source".
- Cosmos Semantic is Apache 2.0, so depending on it from BSL code is allowed; its NOTICE obligations are kept.
- External code contributions are not accepted until a Contributor License Agreement exists, because selling commercial licenses requires rights the BSL alone does not grant over contributed code. Issues and discussion are welcome.
- Private helpers imported from Cosmos Semantic (`_expand_env`, `_sensitivity`) are a coupling risk. They are pinned by the version range and should become public functions in Cosmos Semantic through a pull request there.
- This is not legal advice; the license choice should be reviewed by a lawyer before the first commercial sale.
