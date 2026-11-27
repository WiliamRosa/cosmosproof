"""The audit cycle across many resources (ADR 0010): discover, merge the selection, scan every
selected workspace with the ADLS accounts it uses, record everything in `cosmosproof.audit`
and export the metric model to Parquet.

Layout under the audit location (an abfss:// URL CosmosProof owns, or a local folder):

    cosmosproof.audit       the DuckDB store (the scanner is its only writer)
    selection.json          what to analyze; written by the app, never overwritten here
    model/<name>.parquet    the exported model, for Databricks, Power BI or any tool
"""

from __future__ import annotations

import json
import tempfile
import traceback
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from cosmos_semantic.connectors import _expand_env
from pydantic import BaseModel, ConfigDict, Field

from cosmosproof import __version__
from cosmosproof.config import AccessLogs, DatabricksConfig, Rates, ScanConfig, StorageConfig
from cosmosproof.discovery import (
    Resource,
    enrich_workspace,
    pick_warehouse,
    query_graph,
    selected_by_default,
)
from cosmosproof.publish import Target, target_for
from cosmosproof.scan import AZURE_DATABRICKS_RESOURCE, run_scan
from cosmosproof.store import FILE_NAME, AuditStore

SELECTION = "selection.json"


class DiscoveryScope(BaseModel):
    """Leave both empty to cover every subscription the identity can read."""

    model_config = ConfigDict(extra="forbid")

    subscriptions: list[str] = []
    management_groups: list[str] = []


class StorageDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_tracking_since: date | None = None
    access_logs: AccessLogs | None = None


class AuditConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str = Field(description="Where cosmosproof.audit, selection.json and model/ live.")
    discovery: DiscoveryScope = DiscoveryScope()
    window_days: int = Field(180, ge=1)
    window_hours: float | None = Field(None, gt=0)
    exclude_catalogs: list[str] = ["samples"]
    storage: StorageDefaults = StorageDefaults()
    rates: Rates | None = None
    list_price_discount: float = Field(0.0, ge=0, lt=1)
    max_rows: int = 1_000_000


def parse_audit_config(text: str) -> AuditConfig:
    return AuditConfig.model_validate(_expand_env(yaml.safe_load(text) or {}))


def _token(scope: str) -> str:
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return credential.get_token(f"{scope}/.default").token


def merge_selection(resources: list[Resource], current: dict) -> dict:
    """New resources get the suggested default; choices already made are never changed."""
    chosen = dict(current.get("resources", {}))
    for r in resources:
        chosen.setdefault(r.id, {"selected": selected_by_default(r), "by": "suggestion"})
    return {**current, "resources": chosen}


def discover(config: AuditConfig, target: Target) -> tuple[list[Resource], dict]:
    resources = query_graph(
        _token("https://management.azure.com"),
        config.discovery.subscriptions or None,
        config.discovery.management_groups or None,
    )
    databricks_token = _token(AZURE_DATABRICKS_RESOURCE)
    for r in resources:
        if r.kind == "workspace" and r.host:
            enrich_workspace(r, databricks_token)
    current = json.loads(target.read(SELECTION) or "{}")
    selection = merge_selection(resources, current)
    if selection != current:
        target.write(SELECTION, json.dumps(selection, indent=2))
    return resources, selection


def _account_containers(url: str) -> tuple[str, str] | None:
    # abfss://<container>@<account>.dfs.core.windows.net/...
    try:
        container, rest = url.split("://", 1)[1].split("@", 1)
    except ValueError:
        return None
    return rest.split(".", 1)[0], container


def scan_config_for(
    workspace: Resource, storage_selected: set[str], warehouse_id: str, config: AuditConfig
) -> ScanConfig:
    own = _account_containers(config.location) if config.location.startswith("abfss://") else None
    containers = sorted(
        {
            pair
            for url in workspace.locations
            if (pair := _account_containers(url)) and pair[0] in storage_selected and pair != own
        }
    )
    return ScanConfig(
        window_days=config.window_days,
        window_hours=config.window_hours,
        exclude_catalogs=config.exclude_catalogs,
        rates=config.rates,
        databricks=DatabricksConfig(
            source={
                "type": "databricks",
                "max_rows": config.max_rows,
                "timeout_seconds": 600,
                "options": {
                    "server_hostname": workspace.host,
                    "http_path": f"/sql/1.0/warehouses/{warehouse_id}",
                    "auth": "azure",
                },
            },
            list_price_discount=config.list_price_discount,
        ),
        storage=[
            StorageConfig(
                account=account,
                container=container,
                list_directly=True,
                access_tracking_since=config.storage.access_tracking_since,
                access_logs=config.storage.access_logs,
            )
            for account, container in containers
        ],
    )


def run_audit(
    config: AuditConfig, *, discovered: tuple[list[Resource], dict] | None = None
) -> dict:
    """One full cycle. Returns a summary; never stops on one failing resource."""
    target = target_for(config.location)
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%S") + f"{started.microsecond // 1000:03d}Z"
    resources, selection = discovered or discover(config, target)
    chosen = {rid: v.get("selected", False) for rid, v in selection.get("resources", {}).items()}
    storage_selected = {r.name for r in resources if r.kind == "storage" and chosen.get(r.id)}

    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / FILE_NAME
        etag = target.download(FILE_NAME, local)
        findings = []
        scanned = failed = 0
        with AuditStore(local) as store:
            store.upsert_resources(resources, chosen)
            store.log(run_id, "info", f"{len(resources)} resources discovered")
            for ws in [r for r in resources if r.kind == "workspace" and chosen.get(r.id)]:
                override = selection["resources"].get(ws.id, {}).get("warehouse_id")
                warehouse = override or (pick_warehouse(ws.warehouses) or {}).get("id")
                if ws.status != "ready" or not warehouse:
                    failed += 1
                    reason = ws.error or "no SQL warehouse visible to CosmosProof"
                    store.record_resource_scan(run_id, ws.id, status="error", error=reason)
                    store.log(run_id, "error", reason, ws.id)
                    continue
                try:
                    report = run_scan(scan_config_for(ws, storage_selected, warehouse, config))
                except Exception as exc:  # one workspace must not stop the others
                    failed += 1
                    message = f"{type(exc).__name__}: {exc}"[:500]
                    store.record_resource_scan(run_id, ws.id, status="error", error=message)
                    store.log(
                        run_id, "error", message + "\n" + traceback.format_exc()[-800:], ws.id
                    )
                    continue
                scanned += 1
                findings.extend((ws.id, f) for f in report.findings)
                store.record_resource_scan(run_id, ws.id, status="ok", report=report)
                store.log(run_id, "info", f"{len(report.findings)} findings", ws.id)
            window = config.window_hours / 24 if config.window_hours else config.window_days
            counts = store.record_run(
                run_id, started, __version__, window, findings, scanned, failed
            )
            kpis = store.kpis()
            model = store.export_parquet(Path(tmp) / "model")
        target.upload(FILE_NAME, local, etag)
        for path in model:
            target.upload(f"model/{path.name}", path, _current_etag(target, f"model/{path.name}"))
    return {"run_id": run_id, "scanned": scanned, "failed": failed, **counts, "kpis": kpis}


def _current_etag(target: Target, name: str) -> str | None:
    """The export is derived data, rewritten every run: replace whatever version is there."""
    with tempfile.TemporaryDirectory() as tmp:
        return target.download(name, Path(tmp) / "x")
