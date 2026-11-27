"""Command line: `cosmosproof scan`, `demo`, `diff` and `ledger`."""

from __future__ import annotations

from pathlib import Path

import typer

from cosmosproof import __version__
from cosmosproof.config import load_config, parse_config
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
    cost = "".join(f", {v:.2f} {c}/month" for c, v in totals["monthly_cost"].items())
    typer.echo(f"{totals['findings']} findings{cost}", err=True)


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


@app.command()
def scan(
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="cosmosproof.yml. Without it, the YAML is read from the COSMOSPROOF_CONFIG variable.",
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="Write the report as JSON."),
    markdown: Path | None = typer.Option(
        None, "--markdown", "-m", help="Write the report as Markdown."
    ),
    publish_to: str | None = typer.Option(
        None, "--publish", help="Publish the run for monitoring (overrides `publish`)."
    ),
) -> None:
    """Scan Unity Catalog and ADLS inventories and report unused data with evidence."""
    import os

    from cosmosproof.scan import ScanError, run_scan

    if config is not None:
        settings = load_config(config)
    elif os.environ.get("COSMOSPROOF_CONFIG"):
        settings = parse_config(os.environ["COSMOSPROOF_CONFIG"])
    else:
        raise typer.BadParameter("give --config or set COSMOSPROOF_CONFIG")
    try:
        report = run_scan(settings)
    except ScanError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    _write(report, out, markdown)
    location = publish_to or settings.publish
    if location:
        from cosmosproof.publish import publish, target_for

        counts = publish(report, target_for(location))
        typer.echo(
            f"published to {location}: {counts['new']} new, {counts['ongoing']} ongoing, "
            f"{counts['resolved']} resolved",
            err=True,
        )


@app.command()
def demo(
    out: Path | None = typer.Option(None, "--out", "-o"),
    markdown: Path | None = typer.Option(None, "--markdown", "-m"),
    window_days: int = typer.Option(180, help="No read in this many days means unused."),
) -> None:
    """Run on a fictional bank lake, no Databricks or Azure needed."""
    from cosmosproof.demo import demo_report

    _write(demo_report(window_days), out, markdown)


@app.command()
def grants(
    application_id: str = typer.Option(
        ..., help="Application (client) ID of CosmosProof's identity, as added to Databricks."
    ),
    object_id: str = typer.Option(..., help="Object (principal) ID of the same identity."),
    subscription: str = typer.Option(..., help="Azure subscription ID of the storage accounts."),
    storage: list[str] = typer.Option(
        [], "--storage", help="<resource-group>/<account>; repeat for each account."
    ),
    catalog: list[str] = typer.Option([], "--catalog", help="Catalog to scan; repeat."),
    container: str = typer.Option("cosmosproof-inventory", help="Container for inventory reports."),
    schedule: str = typer.Option("weekly", help="Inventory schedule: daily or weekly."),
) -> None:
    """Print the grants and setup commands for a person to review and run."""
    from cosmosproof.onboarding import StorageAccount, onboarding_script

    if schedule not in {"daily", "weekly"}:
        raise typer.BadParameter("schedule must be daily or weekly")
    try:
        accounts = [StorageAccount.parse(s) for s in storage]
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        onboarding_script(
            application_id=application_id,
            object_id=object_id,
            subscription=subscription,
            accounts=accounts,
            catalogs=catalog,
            container=container,
            schedule=schedule,
        )
    )


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
