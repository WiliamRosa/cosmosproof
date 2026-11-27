# CosmosProof lab

Fictional data in ADLS Gen2 and Unity Catalog that covers the situations CosmosProof must judge, plus two daily jobs that make some of it "used". All names, CPFs and emails are generated.

## Deploy

Needs a Unity Catalog external location over the `--lake` URL and a SQL warehouse.

```bash
pip install "cosmosproof[databricks]"
DATABRICKS_TOKEN=<token> python lab/deploy.py \
  --host adb-<id>.<n>.azuredatabricks.net \
  --warehouse-id <warehouse id> \
  --lake abfss://<container>@<account>.dfs.core.windows.net/lab
```

On Azure an Entra ID token works as `DATABRICKS_TOKEN`:
`az account get-access-token --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d --query accessToken -o tsv`.

Then enable last access tracking on the storage account (`cosmosproof grants` prints the command) and, to test tier costs, move the data files of `archive/historico_2020` to Cool.

It creates the `cosmosproof_lab` catalog and two jobs on the warehouse:

| Job | When (UTC) | Does |
|---|---|---|
| `cosmosproof-lab-producer` | 08:00 | Appends to `bronze.eventos_cdc` and `bronze.transacoes_raw`, rebuilds `gold.receita_diaria` from the latter |
| `cosmosproof-lab-consumer` | 09:00 | Reads `silver.contas_ativas`, `gold.receita_diaria`, the `exports/parceiro_x` path, and `COUNT(*)` on `silver.saldos`; turns the result cache off |

## Scenarios and expected verdicts

| # | Asset | Situation | With lineage | Storage-only mode |
|---|---|---|---|---|
| S1 | `silver.contas_ativas` | Read every day | No finding | No finding |
| S2 | `raw.clientes_legado_2019` | Personal data, never read | Unused table + LGPD, high | Unused table + LGPD, medium |
| S3 | `bronze.eventos_cdc` | Written every day, never read | Unused table, still fed; the producer job is dead | Unused table, medium |
| S4 | `bronze.transacoes_raw` | Read only by the job that builds a used gold table | No finding | No finding |
| S5 | `exports/campanha_2024` | Files no table owns, never read | Orphan path | Orphan path, medium |
| S6 | `exports/parceiro_x` | Files no table owns, read by path every day | No finding | No finding |
| S7 | `archive.historico_2020` | Never read, data files in Cool | Unused table, Cool cost | Unused table, medium, Cool cost |
| S8 | `gold.relatorio_antigo` | Managed table, never read | Unused table | Unused table, medium |
| S9 | `raw.clientes_copia` | Copy of S2 | Unused table + LGPD | Unused table + LGPD, medium |
| S10 | `silver.saldos` | Only `COUNT(*)` every day | No finding | **Unused table (false positive)**: `COUNT(*)` is answered from Delta statistics and touches no data file |

S10 is there on purpose: it shows the main limit of storage-only mode, which every Delta finding states.

## When results mean something

Tables created inside the window are never judged, and last access tracking only records from the day it is enabled. With the lab deployed and tracking enabled on day D, scan with `window_days: 2` from day D+3: the window then starts after both, and the consumer has run on every day of it.

## Tear down

```sql
DROP CATALOG cosmosproof_lab CASCADE;
```

Then delete the two jobs and the `lab/` folder in the container (external tables keep their files after `DROP`):

```bash
az storage fs directory delete --account-name <account> -f <container> -n lab --auth-mode login --yes
```
