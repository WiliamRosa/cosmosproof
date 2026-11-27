# Scheduled scans on Azure

`monitor.bicep` deploys an Azure Container Apps Job that runs the CosmosProof scanner daily with a user-assigned managed identity ([ADR 0007](../../docs/decisions/0007-continuous-monitoring.md)).

## What the identity needs

Print the grants with `cosmosproof grants`, then add, for the monitoring loop:

| Grant | Scope |
|---|---|
| AcrPull | The container registry holding the image |
| Storage Blob Data Contributor | **Only** the container CosmosProof publishes to |
| CAN USE | The SQL warehouse (Databricks permissions) |

## Build and deploy

```bash
az acr build -r <registry> -t cosmosproof:<tag> .
az deployment group create -g <resource-group> --template-file deploy/azure/monitor.bicep \
  --parameters identityName=<identity> registryServer=<registry>.azurecr.io \
               image=<registry>.azurecr.io/cosmosproof:<tag> scanConfig=@cosmosproof.yml
```

The scan configuration should hold no credential: use `options.auth: azure` for Databricks and `list_directly: true` for storage, and set `publish:` to an `abfss://` URL in the reports container. On Git Bash for Windows, prefix `az` commands with `MSYS_NO_PATHCONV=1`.

Run once without waiting for the schedule:

```bash
az rest --method post --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.App/jobs/cosmosproof-scan/start?api-version=2024-03-01"
```

## Dashboard on Databricks

After the first published run, create the Unity Catalog views and the AI/BI dashboard over the publish location (it needs a read-only external location over it):

```bash
DATABRICKS_TOKEN=<token> python deploy/databricks/dashboard.py --host <workspace host> \
  --warehouse-id <id> --publish abfss://<container>@<account>.dfs.core.windows.net/<path> \
  --schema <catalog>.<schema>
```

## Alerts on Azure

Each run logs one line such as `published to ...: 2 new, 5 ongoing, 1 resolved` to the Log Analytics workspace. An Azure Monitor log alert on this query raises an alert when new waste appears; route it to an action group of your choice:

```kusto
ContainerAppConsoleLogs_CL
| where Log_s has "published to"
| extend new_findings = toint(extract(@": (\d+) new", 1, Log_s))
| where new_findings > 0
```

## What the identity also needs on Databricks

Besides `CAN USE` on the warehouse, the service principal needs the **Databricks SQL access** entitlement (`databricks-sql-access`); without it every connection fails with "This API is disabled for users without the databricks-sql-access or workspace-consume entitlements".
