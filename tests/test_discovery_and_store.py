from datetime import UTC, datetime

import duckdb
import pytest

from cosmosproof.demo import demo_report
from cosmosproof.discovery import (
    Resource,
    parse_graph_rows,
    pick_warehouse,
    selected_by_default,
    storage_used_by,
    suggest_environment,
)
from cosmosproof.store import FILE_NAME, AuditStore

WS = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Databricks/workspaces/"
SA = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/"


@pytest.mark.parametrize(
    ("name", "tags", "expected"),
    [
        ("wkp-dbx-prd-01", {}, ("prod", "name")),
        ("dbx-poc-credito", {}, ("poc", "name")),
        ("dlsandboxrisk", {}, ("unknown", "none")),  # no separator: not guessed
        ("dl-sandbox-risk", {}, ("poc", "name")),
        ("lake-hml", {}, ("test", "name")),
        ("lake-core", {"Environment": "Production"}, ("prod", "tag")),
        ("lake-prod", {"ambiente": "desenv"}, ("dev", "tag")),  # tags win over names
        ("lake-core", {"env": "shared"}, ("unknown", "tag")),
    ],
)
def test_environment_suggestion(name, tags, expected):
    assert suggest_environment(name, tags) == expected


def test_graph_rows_and_defaults():
    rows = [
        {"id": WS + "wkp-prd", "name": "wkp-prd", "type": "microsoft.databricks/workspaces",
         "resourceGroup": "rg", "subscriptionId": "s", "location": "brazilsouth", "tags": {},
         "workspaceUrl": "adb-1.1.azuredatabricks.net"},
        {"id": SA + "lakedev", "name": "lake-dev", "type": "microsoft.storage/storageaccounts",
         "resourceGroup": "rg", "subscriptionId": "s", "location": "brazilsouth", "tags": None,
         "workspaceUrl": ""},
    ]  # fmt: skip
    ws, sa = sorted(parse_graph_rows(rows), key=lambda r: r.kind, reverse=True)
    assert (ws.kind, ws.host, ws.environment) == (
        "workspace",
        "adb-1.1.azuredatabricks.net",
        "prod",
    )
    assert (sa.kind, sa.host, sa.environment) == ("storage", None, "dev")
    assert selected_by_default(ws) and not selected_by_default(sa)


def test_warehouse_choice_and_storage_links():
    assert (
        pick_warehouse(
            [
                {"id": "big", "cluster_size": "Large", "state": "RUNNING"},
                {
                    "id": "srv",
                    "cluster_size": "Small",
                    "state": "STOPPED",
                    "enable_serverless_compute": True,
                },
            ]
        )["id"]
        == "srv"
    )
    a = Resource(
        "1",
        "workspace",
        "a",
        "s",
        "rg",
        "l",
        locations=["abfss://lake@acct1.dfs.core.windows.net/"],
    )
    b = Resource(
        "2", "workspace", "b", "s", "rg", "l", locations=["abfss://x@acct1.dfs.core.windows.net/p"]
    )
    assert storage_used_by([a, b]) == {"acct1": ["a", "b"]}


def test_store_runs_statuses_metrics_and_export(tmp_path):
    report = demo_report()
    ws = Resource(
        WS + "wkp-prd", "workspace", "wkp-prd", "s", "rg", "brazilsouth", environment="prod"
    )
    with AuditStore(tmp_path / FILE_NAME) as store:
        store.upsert_resources([ws], {ws.id: True})
        store.upsert_resources([ws], {ws.id: True})  # idempotent
        assert len(store.resources()) == 1

        first = store.record_run(
            "20261127T100000Z", datetime(2026, 11, 27, 10, tzinfo=UTC), "t", 180,
            [(ws.id, f) for f in report.findings], 1, 0,
        )  # fmt: skip
        assert first == {"new": len(report.findings), "ongoing": 0, "resolved": 0}
        store.record_resource_scan("20261127T100000Z", ws.id, status="ok", report=report)

        # Next run: one finding gone, and the same findings seen again from a second workspace.
        later = [(ws.id, f) for f in report.findings[1:]] + [("other", report.findings[1])]
        second = store.record_run(
            "20261128T100000Z", datetime(2026, 11, 28, 10, tzinfo=UTC), "t", 180, later, 2, 0
        )
        assert second == {"new": 0, "ongoing": len(report.findings) - 1, "resolved": 1}

        kpis = store.kpis()
        assert kpis["open_findings"] == len(report.findings) - 1
        assert kpis["resolved_findings"] == 1
        assert kpis["pii_findings"] == 1 and kpis["currency"] == "USD"
        files = store.export_parquet(tmp_path / "model")
    assert {f.stem for f in files} >= {"fact_finding", "v_kpis", "v_trend", "v_resource_health"}
    trend = duckdb.sql(
        f"SELECT COUNT(*) FROM '{(tmp_path / 'model' / 'v_trend.parquet').as_posix()}'"
    )
    assert trend.fetchall()[0][0] == 2


def test_metric_views_have_one_row_per_owner_and_bi_friendly_types(tmp_path):
    report = demo_report()
    with AuditStore(tmp_path / FILE_NAME) as store:
        store.record_run(
            "r1",
            datetime(2026, 11, 27, tzinfo=UTC),
            "t",
            180,
            [("ws", f) for f in report.findings],
            1,
            0,
        )
        owners = store.con.execute("SELECT owner FROM v_cost_by_owner").fetchall()
        assert len(owners) == len(set(owners))
        types = dict(store.con.execute("DESCRIBE v_kpis").fetchall()[i][:2] for i in range(10))
        assert types["unused_bytes"] == "BIGINT"


def test_workspace_managed_storage_follows_its_workspace_and_starts_unselected():
    rows = [
        {"id": WS + "wkp-prd", "name": "wkp-prd", "type": "microsoft.databricks/workspaces",
         "resourceGroup": "rg", "subscriptionId": "s", "location": "l", "tags": {},
         "workspaceUrl": "adb-1.1.azuredatabricks.net",
         "managedResourceGroup": "/subscriptions/s/resourceGroups/RG-PRD-MANAGED"},
        {"id": "/x/dbstorageabc", "name": "dbstorageabc", "type": "microsoft.storage/storageaccounts",
         "resourceGroup": "rg-prd-managed", "subscriptionId": "s", "location": "l", "tags": {},
         "workspaceUrl": "", "managedResourceGroup": ""},
    ]  # fmt: skip
    storage = next(r for r in parse_graph_rows(rows) if r.kind == "storage")
    assert (storage.managed_by, storage.environment, storage.environment_source) == (
        "wkp-prd",
        "prod",
        "workspace",
    )
    assert not selected_by_default(storage)
