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
    assert kinds == {"unused_table", "orphan_path", "unused_personal_data"}
    assert "main.silver.contas" not in {f.asset for f in report.findings}
    assert report.totals()["monthly_cost"] > 0
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
    }
    cost = next(f for f in report.findings if f.reading == "cost")
    assert cost.monthly_cost == 0.02 and cost.confidence == "high"
    assert cost.details["still_fed"] is True
    assert LOC in cost.details["storage_path"]


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
