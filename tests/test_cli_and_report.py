import json

from conftest import LOC, NAMES, REFERENCE
from typer.testing import CliRunner

from cosmosproof.cli import app
from cosmosproof.config import DatabricksConfig, Rates, ScanConfig, StorageConfig
from cosmosproof.demo import demo_report
from cosmosproof.report import diff, to_markdown
from cosmosproof.scan import run_scan

runner = CliRunner()


def test_demo_report_has_all_kinds():
    report = demo_report()
    kinds = {f.kind for f in report.findings}
    assert kinds == {"unused_table", "orphan_path", "unused_personal_data", "unused_producer"}
    assert "main.silver.contas" not in {f.asset for f in report.findings}
    assert report.totals()["monthly_cost"]["USD"] > 0
    assert "Compliance (LGPD)" in to_markdown(report)


def test_scan_end_to_end_on_duckdb(duck, tmp_path):
    inv = tmp_path / "inv.csv"
    inv.write_text(
        "Name,Content-Length,AccessTier,Last-Modified,LastAccessTime\n"
        "raw/clientes/p.parquet,1073741824,Hot,2025-01-01T00:00:00Z,2026-01-11T00:00:00Z\n"
        "silver/contas/p.parquet,1073741824,Hot,2026-11-24T00:00:00Z,2026-11-25T00:00:00Z\n",
        encoding="utf-8",
    )
    config = ScanConfig(
        reference_date=REFERENCE,
        databricks=DatabricksConfig(source={"type": "duckdb"}, system_tables=NAMES),
        storage=[
            StorageConfig(
                account="acct",
                container="lake",
                inventory=str(inv),
                access_tracking_since="2025-01-01",
            )
        ],
        rates=Rates(per_gb_month={"hot": 0.02}),
    )
    report = run_scan(config, connector=duck)
    assets = {(f.kind, f.asset) for f in report.findings}
    assert assets == {
        ("unused_table", "main.raw.clientes"),
        ("unused_personal_data", "main.raw.clientes"),
        ("unused_producer", "job 7 (carga clientes)"),
    }
    cost = next(f for f in report.findings if f.kind == "unused_table")
    assert cost.monthly_cost == 0.02 and cost.confidence == "high"
    assert cost.details["still_fed"] is True
    # job 7 reads its own output: that read must not make the table look used.
    assert cost.details["last_read"].startswith("2026-01-10")
    assert cost.details["fed_by"] == ["job 7 (carga clientes)", "job 8 (retired job)"]
    assert LOC in cost.details["storage_path"]

    producer = next(f for f in report.findings if f.kind == "unused_producer")
    assert producer.owner == "etl@bank" and producer.confidence == "medium"
    assert producer.monthly_cost == round(7.0 / 180 * 30, 2) and producer.currency == "USD"
    assert producer.details["tables"].keys() == {"main.raw.clientes"}
    assert report.totals()["monthly_cost"] == {"USD": round(0.02 + producer.monthly_cost, 2)}
    assert any("pipeline:p1 has no list price" in n for n in report.coverage_notes)


def test_scan_without_producers(duck):
    config = ScanConfig(
        reference_date=REFERENCE,
        databricks=DatabricksConfig(
            source={"type": "duckdb"}, system_tables=NAMES, producers=False
        ),
    )
    kinds = {f.kind for f in run_scan(config, connector=duck).findings}
    assert "unused_producer" not in kinds


def test_cli_demo_diff_and_ledger(tmp_path):
    first, second, ledger = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "l.jsonl"
    assert runner.invoke(app, ["demo", "-o", str(first)]).exit_code == 0
    assert runner.invoke(app, ["demo", "-o", str(second), "--window-days", "400"]).exit_code == 0
    a = json.loads(first.read_text(encoding="utf-8"))
    result = runner.invoke(app, ["diff", str(first), str(second)])
    assert result.exit_code == 0 and "resolved:" in result.output

    fid = a["findings"][0]["id"]
    added = runner.invoke(
        app,
        [
            "ledger",
            "add",
            "-r",
            str(first),
            "-f",
            fid,
            "-a",
            "moved to Cool",
            "--by",
            "dpo",
            "-l",
            str(ledger),
        ],
    )
    assert added.exit_code == 0, added.output
    summary = runner.invoke(app, ["ledger", "summary", "-l", str(ledger)])
    assert "actions: 1" in summary.output and "USD" in summary.output


def test_diff_classifies():
    full = demo_report(180)
    shorter = full.model_copy(update={"findings": full.findings[1:]})
    result = diff(full, shorter)
    assert result["resolved"] == [full.findings[0].id]
    assert result["new"] == []


def test_list_price_discount(duck):
    config = ScanConfig(
        reference_date=REFERENCE,
        databricks=DatabricksConfig(
            source={"type": "duckdb"}, system_tables=NAMES, list_price_discount=0.25
        ),
    )
    producer = next(
        f for f in run_scan(config, connector=duck).findings if f.kind == "unused_producer"
    )
    assert producer.monthly_cost == round(7.0 * 0.75 / 180 * 30, 2)
    assert any("25% discount" in n for n in producer.coverage_notes)


def test_missing_system_table_grants_give_a_clear_error():
    import pytest
    from cosmos_semantic.connectors import Connector, DataSourceConfig
    from cosmos_semantic.errors import ConnectorError

    from cosmosproof.scan import ScanError

    class Denied(Connector):
        def _run(self, sql, fetch_limit):
            raise ConnectorError("[INSUFFICIENT_PERMISSIONS] no USE SCHEMA on system.access")

    config = ScanConfig(databricks=DatabricksConfig(source={"type": "duckdb"}))
    with pytest.raises(ScanError, match="BROWSE"):
        run_scan(config, connector=Denied(DataSourceConfig(type="duckdb")))


def test_storage_only_mode_when_lineage_is_denied(duck, tmp_path):
    from cosmos_semantic.connectors import Connector, DataSourceConfig
    from cosmos_semantic.errors import ConnectorError

    class LineageDenied(Connector):
        def _run(self, sql, fetch_limit):
            if "uc_lineage" in sql:
                raise ConnectorError("[INSUFFICIENT_PERMISSIONS] no USE SCHEMA on system.access")
            return duck._run(sql, fetch_limit)

    inv = tmp_path / "inv.csv"
    inv.write_text(
        "Name,Content-Length,AccessTier,Last-Modified,LastAccessTime\n"
        "raw/clientes/p.parquet,1073741824,Hot,2025-01-01T00:00:00Z,2026-01-11T00:00:00Z\n"
        # A writer reading the log must not make the table look read.
        "raw/clientes/_delta_log/00001.json,10,Hot,2026-11-25T00:00:00Z,2026-11-25T00:00:00Z\n"
        "silver/contas/p.parquet,1073741824,Hot,2026-11-24T00:00:00Z,2026-11-25T00:00:00Z\n",
        encoding="utf-8",
    )
    config = ScanConfig(
        reference_date=REFERENCE,
        databricks=DatabricksConfig(source={"type": "duckdb"}, system_tables=NAMES),
        storage=[
            StorageConfig(
                account="acct",
                container="lake",
                inventory=str(inv),
                access_tracking_since="2025-01-01",
            )
        ],
    )
    report = run_scan(config, connector=LineageDenied(DataSourceConfig(type="duckdb")))
    kinds = {(f.kind, f.asset) for f in report.findings}
    assert kinds == {
        ("unused_table", "main.raw.clientes"),
        ("unused_personal_data", "main.raw.clientes"),
    }
    assert all(f.confidence == "medium" for f in report.findings)
    assert all(
        not any(e.source.startswith("system.access") for e in f.evidence) for f in report.findings
    )
    assert any("Storage-only mode" in n for n in report.coverage_notes)
    clientes = next(f for f in report.findings if f.kind == "unused_table")
    assert any("Only data files count" in n for n in clientes.coverage_notes)
