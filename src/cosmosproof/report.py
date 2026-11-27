"""Report rendering (JSON and Markdown), comparison between runs, and the savings ledger."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from cosmosproof.model import Report

READING_TITLES = {
    "cost": "Cost (FinOps)",
    "risk": "Risk",
    "compliance": "Compliance (LGPD)",
}


def _size(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def to_markdown(report: Report) -> str:
    totals = report.totals()
    window = (
        f"{report.window_days * 24:g} hours"
        if report.window_days < 1
        else f"{report.window_days:g} days"
    )
    lines = [
        "# CosmosProof report",
        "",
        f"Reference date: {report.reference_date.isoformat()} · window: {window} · "
        f"generated {report.generated_at.isoformat(timespec='seconds')} · CosmosProof {report.tool_version}",
        "",
        "## Summary",
        "",
        f"- Findings: {totals['findings']} "
        f"(cost {totals['by_reading']['cost']}, risk {totals['by_reading']['risk']}, "
        f"compliance {totals['by_reading']['compliance']})",
        "- Unused storage: "
        + (
            _size(totals["unused_bytes"])
            if report.storage_files
            else "unknown (no inventory or listing)"
        ),
    ]
    for currency, value in totals["monthly_cost"].items():
        lines.append(f"- Estimated monthly cost (storage and compute): {value:.2f} {currency}")
    if report.coverage_notes:
        lines += ["", "**Coverage notes for the whole run:**", ""]
        lines += [f"- {note}" for note in report.coverage_notes]
    for reading, title in READING_TITLES.items():
        items = [f for f in report.findings if f.reading == reading]
        if not items:
            continue
        lines += ["", f"## {title}", ""]
        for f in items:
            cost = (
                f" · {f.monthly_cost:.2f} {f.currency}/month" if f.monthly_cost is not None else ""
            )
            lines += [
                f"### {f.asset}",
                "",
                f"`{f.kind}` · confidence **{f.confidence}** · owner {f.owner or 'unknown'}"
                + (f" · {_size(f.size_bytes)}" if f.size_bytes else "")
                + cost,
                "",
                "Evidence:",
            ]
            for e in f.evidence:
                when = f" ({e.observed_at.date().isoformat()})" if e.observed_at else ""
                lines.append(f"- {e.source}: {e.signal}{when}")
            if f.coverage_notes:
                lines += ["", "What could not be seen:"]
                lines += [f"- {n}" for n in f.coverage_notes]
            lines += [
                "",
                f"Recommendation: {f.recommendation}",
                "",
                f"Proof: `{f.proof_hash}` · id `{f.id}`",
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def load_report(path: str | Path) -> Report:
    return Report.model_validate_json(Path(path).read_text(encoding="utf-8"))


def diff(previous: Report, current: Report) -> dict[str, list[str]]:
    """New findings are the alerts; resolved ones are candidates for the savings ledger."""
    before = {f.id: f for f in previous.findings}
    after = {f.id: f for f in current.findings}
    return {
        "new": sorted(after.keys() - before.keys()),
        "resolved": sorted(before.keys() - after.keys()),
        "ongoing": sorted(after.keys() & before.keys()),
    }


class LedgerEntry(BaseModel):
    finding_id: str
    proof_hash: str
    asset: str
    action: str = Field(description="What was done, e.g. moved to Cool, dropped, anonymized.")
    monthly_saving: float | None = None
    currency: str | None = None
    by: str
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def ledger_append(path: str | Path, entry: LedgerEntry) -> None:
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def ledger_read(path: str | Path) -> list[LedgerEntry]:
    file = Path(path)
    if not file.exists():
        return []
    return [
        LedgerEntry.model_validate(json.loads(line))
        for line in file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
