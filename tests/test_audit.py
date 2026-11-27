import json

from cosmosproof.audit import (
    AuditConfig,
    merge_selection,
    parse_audit_config,
    run_audit,
    scan_config_for,
)
from cosmosproof.discovery import Resource
from cosmosproof.publish import ConcurrentUpdateError, LocalTarget
from cosmosproof.store import FILE_NAME, AuditStore

WS = Resource(
    "/ws/prd", "workspace", "wkp-prd", "s", "rg", "l", environment="prod",
    host="adb-1.1.azuredatabricks.net", status="ready",
    warehouses=[{"id": "abc123", "cluster_size": "Small", "state": "STOPPED", "enable_serverless_compute": True}],
    locations=[
        "abfss://lake@acct1.dfs.core.windows.net/",
        "abfss://raw@acct1.dfs.core.windows.net/x",
        "abfss://lake@acct2.dfs.core.windows.net/",
        "abfss://cosmosproof-reports@acct1.dfs.core.windows.net/",
    ],
)  # fmt: skip
DEV = Resource("/ws/dev", "workspace", "wkp-dev", "s", "rg", "l", environment="dev")
SA1 = Resource("/sa/acct1", "storage", "acct1", "s", "rg", "l", environment="prod")
SA2 = Resource("/sa/acct2", "storage", "acct2", "s", "rg", "l", environment="poc")


def test_selection_keeps_choices_and_suggests_for_new():
    current = {"resources": {"/ws/dev": {"selected": True, "by": "maria"}}}
    merged = merge_selection([WS, DEV, SA1, SA2], current)["resources"]
    assert merged["/ws/dev"] == {"selected": True, "by": "maria"}  # never overwritten
    assert merged["/ws/prd"]["selected"] and merged["/sa/acct1"]["selected"]
    assert not merged["/sa/acct2"]["selected"]


def test_scan_config_uses_selected_storage_only_and_skips_own_container():
    config = AuditConfig(location="abfss://cosmosproof-reports@acct1.dfs.core.windows.net/audit")
    scan = scan_config_for(WS, {"acct1"}, "abc123", config)
    assert [(s.account, s.container) for s in scan.storage] == [("acct1", "lake"), ("acct1", "raw")]
    assert scan.databricks.source.options["auth"] == "azure"
    assert scan.databricks.source.options["http_path"] == "/sql/1.0/warehouses/abc123"


def test_audit_cycle_records_failures_without_stopping(tmp_path, monkeypatch):
    import cosmosproof.audit as audit
    from cosmosproof.demo import demo_report

    ws_down = Resource(
        "/ws/down", "workspace", "wkp-down", "s", "rg", "l", status="error", error="403"
    )
    selection = merge_selection([WS, ws_down, SA1], {})
    monkeypatch.setattr(audit, "run_scan", lambda cfg: demo_report())
    config = parse_audit_config(f"location: {tmp_path.as_posix()}\nwindow_days: 30\n")
    summary = run_audit(config, discovered=([WS, ws_down, SA1], selection))
    assert (summary["scanned"], summary["failed"]) == (1, 1)
    assert summary["kpis"]["open_findings"] == len(demo_report().findings)
    assert (tmp_path / "model" / "v_kpis.parquet").exists()

    with AuditStore(tmp_path / FILE_NAME) as store:
        health = {
            r[0]: r[1]
            for r in store.con.execute(
                "SELECT name, last_scan_status FROM v_resource_health"
            ).fetchall()
        }
    assert health == {"wkp-prd": "ok", "wkp-down": "error", "acct1": None}

    # A second cycle marks findings as ongoing.
    second = run_audit(config, discovered=([WS, ws_down, SA1], selection))
    assert second["ongoing"] == len(demo_report().findings) and second["new"] == 0


def test_concurrent_writers_are_refused(tmp_path):
    target = LocalTarget(tmp_path)
    local = tmp_path / "copy"
    local.write_text("v1")
    target.upload("store", local, None)
    etag = target.download("store", tmp_path / "mine")
    target.upload("store", local, etag)  # someone else writes first
    try:
        target.upload("store", local, etag)
    except ConcurrentUpdateError:
        pass
    else:
        raise AssertionError("an outdated writer must be refused")
    assert json.loads(json.dumps({"ok": True}))["ok"]


def test_old_suggestions_are_recomputed_but_choices_are_not():
    current = {
        "resources": {
            "/sa/acct2": {"selected": True, "by": "suggestion"},  # rule changed since
            "/ws/dev": {"selected": True, "by": "maria"},
        }
    }
    merged = merge_selection([DEV, SA2], current)["resources"]
    assert merged["/sa/acct2"]["selected"] is False
    assert merged["/ws/dev"] == {"selected": True, "by": "maria"}
