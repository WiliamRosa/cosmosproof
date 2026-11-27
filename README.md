# CosmosProof

**We show, with proof, what in your Azure Databricks costs money, creates risk or breaks the LGPD necessity principle without being used.**

Most data lakes keep paying for data nobody reads. Existing tools either optimize compute or flag "unused" tables from a single signal and admit false positives. CosmosProof crosses Unity Catalog lineage with ADLS Gen2 storage activity, only calls something unused when the evidence agrees, and every finding says what it could not see.

One map, three readings:

| Reading | Question |
|---|---|
| Cost (FinOps) | What am I paying for that nobody reads? |
| Risk | Which production credentials and database loads exist with no real use? |
| Compliance (LGPD) | Which personal data is stored with no purpose in use? |

> Status: pre-alpha. Phase 1 (ADLS Gen2 + Unity Catalog + LGPD reading) and phase 2 (jobs and pipelines, including Lakeflow Connect, that feed tables nobody reads, with their compute cost) work and were validated against real Unity Catalog system tables. See the [roadmap](docs/roadmap.md).

## Try it in one minute

```bash
pip install git+https://github.com/WiliamRosa/cosmosproof
cosmosproof demo
```

The demo runs on a fictional bank lake, with no Databricks or Azure needed. A finding looks like this:

```
### main.raw.clientes_legado
`unused_table` · confidence **high** · owner data-eng-legado · 180.0 GB · 3.74 USD/month

Evidence:
- system.access.table_lineage: no read inside the 180-day window; last read 2026-01-20
- Azure Blob Inventory: 40 files, 180.00 GB, by tier: hot 180.00 GB
- Azure Blob Inventory: no file read inside the window; last read 2026-01-25

What could not be seen:
- Unity Catalog lineage records only the reads it can infer; ...

Proof: `sha256:...` · id `ab8825127671`
```

The same table also gets a compliance finding, because it holds `cpf`, `email` and `nome_completo`. And the demo's Lakeflow Connect pipeline that ingests from SQL Server into a table nobody reads shows up with its compute cost: usually the biggest number in the report.

## Scan your own workspace

```bash
pip install "cosmosproof[databricks] @ git+https://github.com/WiliamRosa/cosmosproof"
cosmosproof scan -c cosmosproof.yml -o report.json -m report.md
```

See [examples/cosmosproof.yml](examples/cosmosproof.yml). You need:

- A Databricks SQL warehouse and a principal with `BROWSE` on the catalogs to scan. For lineage, jobs and cost, also `USE` and `SELECT` on the `system` schemas `access`, `lakeflow` and `billing`; only a Databricks account admin can grant those. Without them CosmosProof runs in [storage-only mode](docs/decisions/0006-storage-only-mode.md).
- Storage Blob Data Reader on each ADLS account. Either list it directly (`list_directly: true`, `pip install "cosmosproof[azure]"`) or point to a Blob Inventory report.
- Optionally, [storage read logs](docs/decisions/0008-storage-read-logs.md) in Log Analytics (`access_logs`): every read with its exact time, by any tool.
- For large lakes, one [Blob Inventory](https://learn.microsoft.com/en-us/azure/storage/blobs/blob-inventory) report per ADLS container instead of listing, with `LastAccessTime`, `AccessTier` and `Content-Length`. Without storage data, findings stay at medium confidence and have no size or cost.
- Optionally, [last access time tracking](https://learn.microsoft.com/en-us/azure/storage/blobs/access-tiers-overview) enabled on the storage account. It only records from activation onwards; the Unity Catalog history (about one year) covers the past.

To prepare those grants, `cosmosproof grants` prints every SQL grant and Azure CLI command (read-only roles only) for a person to review and run:

```bash
cosmosproof grants --application-id <app-id> --object-id <object-id> \n  --subscription <sub-id> --storage rg-data/lake01 --catalog main
```

CosmosProof only reads. It never deletes, moves or changes anything, and never runs those commands itself.

## Keep it running

```bash
cosmosproof diff last-week.json today.json   # new findings are alerts, resolved ones are savings
cosmosproof ledger add -r today.json -f ab8825127671 -a "moved to Cool" --by data-eng
cosmosproof ledger summary                   # realized monthly savings, each tied to a proof hash
```

## Monitor it continuously

Run the scanner on a schedule and publish every run to a location CosmosProof owns (`publish:`). Each run writes the full report, one row per finding with its status (new, ongoing, resolved since the previous run) and a run summary. A Databricks AI/BI dashboard reads them through Unity Catalog, and an Azure Monitor alert can fire on new findings. The reference setup runs as an Azure Container Apps Job with a managed identity and no stored credential: see [deploy/azure](deploy/azure/README.md) and [ADR 0007](docs/decisions/0007-continuous-monitoring.md).

## How confidence works

| Confidence | When |
|---|---|
| high | No read in lineage **and** storage last access covers the window and shows no read |
| medium | No read in lineage and storage cannot confirm; or storage no table owns, with storage confirming no read |
| low | Storage no table owns, with no storage confirmation |

If storage shows a read inside the window, there is no finding, even when lineage is silent. Details in [ADR 0004](docs/decisions/0004-evidence-and-confidence-model.md).

## Documentation

- [Lab](lab/README.md): fictional data and daily jobs covering every scenario, to deploy on your own workspace
- [Product proposal](docs/product-proposal.md) ([pt-BR](docs/product-proposal.pt-BR.md))
- [Roadmap](docs/roadmap.md)
- [Decisions](docs/decisions/)

## License

CosmosProof is **source-available** under the [Business Source License 1.1](LICENSE), not open source. You can read, modify and use it for evaluation and other non-production purposes, and in production for non-commercial purposes. Production use by a company requires a commercial license, offered through the Azure Marketplace. Each version converts to Apache 2.0 four years after its release. See [ADR 0002](docs/decisions/0002-repository-license-and-cosmos-dependency.md).

CosmosProof builds on [Cosmos Semantic](https://github.com/WiliamRosa/cosmos-semantic-platform) (Apache 2.0).
