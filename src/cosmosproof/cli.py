"""Command line: `cosmosproof scan`, `demo`, `diff` and `ledger`."""

from __future__ import annotations

from pathlib import Path

import typer

from cosmosproof import __version__
from cosmosproof.config import load_config
from cosmosproof.model import Report
from cosmosproof.report import (
    LedgerEntry,
    diff,
    ledger_append,
    ledger_read,
    load_report,
    to_markdown,
)

app = typer.Typer(
    help="Shows, with proof, what in your Azure Databricks is paid for and unused.",
    no_args_is_help=True,
)
ledger_app = typer.Typer(
    help="Record actions taken on findings and the savings they produced.", no_args_is_help=True
)
app.add_typer(ledger_app, name="ledger")


def _write(report: Report, out: Path | None, markdown: Path | None) -> None:
    if out:
        out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    if markdown:
        markdown.write_text(to_markdown(report), encoding="utf-8")
    if not out and not markdown:
        typer.echo(to_markdown(report))
    totals = report.totals()
    cost = (
        f", {totals['monthly_cost']:.2f} {totals['currency']}/month"
        if totals["monthly_cost"] is not None
        else ""
    )
    typer.echo(f"{totals['findings']} findings{cost}", err=True)


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


@app.command()
def scan(
    config: Path = typer.Option(..., "--config", "-c", help="cosmosproof.yml"),
    out: Path | None = typer.Option(None, "--out", "-o", help="Write the report as JSON."),
    markdown: Path | None = typer.Option(
        None, "--markdown", "-m", help="Write the report as Markdown."
    ),
) -> None:
    """Scan Unity Catalog and ADLS inventories and report unused data with evidence."""
    from cosmosproof.scan import run_scan

    _write(run_scan(load_config(config)), out, markdown)


@app.command()
def demo(
    out: Path | None = typer.Option(None, "--out", "-o"),
    markdown: Path | None = typer.Option(None, "--markdown", "-m"),
    window_days: int = typer.Option(180, help="No read in this many days means unused."),
) -> None:
    """Run on a fictional bank lake, no Databricks or Azure needed."""
    from cosmosproof.demo import demo_report

    _write(demo_report(window_days), out, markdown)


@app.command("diff")
def diff_cmd(previous: Path, current: Path) -> None:
    """Compare two reports: new findings are alerts, resolved ones go to the ledger."""
    old, new = load_report(previous), load_report(current)
    result = diff(old, new)
    assets = {f.id: f.asset for f in [*old.findings, *new.findings]}
    for label in ("new", "resolved"):
        typer.echo(f"{label}: {len(result[label])}")
        for fid in result[label]:
            typer.echo(f"  {fid}  {assets[fid]}")
    typer.echo(f"ongoing: {len(result['ongoing'])}")


@ledger_app.command("add")
def ledger_add(
    report: Path = typer.Option(..., "--report", "-r", help="Report that holds the finding."),
    finding: str = typer.Option(..., "--finding", "-f", help="Finding id."),
    action: str = typer.Option(..., "--action", "-a"),
    by: str = typer.Option(..., "--by"),
    saving: float | None = typer.Option(
        None, "--monthly-saving", help="Defaults to the finding's estimate."
    ),
    ledger: Path = typer.Option(Path("cosmosproof-ledger.jsonl"), "--ledger", "-l"),
) -> None:
    """Record an action taken on a finding, with its proof hash."""
    rep = load_report(report)
    match = next((f for f in rep.findings if f.id == finding), None)
    if match is None:
        raise typer.BadParameter(f"finding {finding} is not in {report}")
    ledger_append(
        ledger,
        LedgerEntry(
            finding_id=match.id,
            proof_hash=match.proof_hash,
            asset=match.asset,
            action=action,
            monthly_saving=saving if saving is not None else match.monthly_cost,
            currency=match.currency,
            by=by,
        ),
    )
    typer.echo(f"recorded {match.id} ({match.asset})")


@ledger_app.command("summary")
def ledger_summary(
    ledger: Path = typer.Option(Path("cosmosproof-ledger.jsonl"), "--ledger", "-l"),
) -> None:
    """Total realized monthly savings."""
    entries = ledger_read(ledger)
    totals: dict[str, float] = {}
    for e in entries:
        if e.monthly_saving is not None and e.currency:
            totals[e.currency] = totals.get(e.currency, 0.0) + e.monthly_saving
    typer.echo(f"actions: {len(entries)}")
    for currency, value in sorted(totals.items()):
        typer.echo(f"monthly savings: {value:.2f} {currency}")


if __name__ == "__main__":
    app()
