"""Publishes each run to a location CosmosProof owns, for continuous monitoring.

Layout under the publish location (ADR 0007):

    runs/<run_id>/report.json     the full report
    findings/<run_id>.jsonl       one row per finding, plus one row per finding resolved since
                                  the previous run, each with a status: new, ongoing, resolved
    summaries/<run_id>.json       one row per run, so runs with no findings still show

This is the only write CosmosProof ever makes, and only to its own location.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from cosmosproof.model import Finding, Report
from cosmosproof.report import diff


class Target(Protocol):
    def read(self, name: str) -> str | None: ...
    def write(self, name: str, text: str) -> None: ...
    def list(self, prefix: str) -> list[str]: ...


class LocalTarget:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def read(self, name: str) -> str | None:
        path = self.root / name
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def list(self, prefix: str) -> list[str]:
        base = self.root / prefix
        if not base.exists():
            return []
        return sorted(p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file())


class AdlsTarget:
    """abfss://<container>@<account>.dfs.core.windows.net/<path>, written with Azure credentials."""

    def __init__(self, url: str) -> None:
        rest = url.split("://", 1)[1]
        container, _, rest = rest.partition("@")
        host, _, path = rest.partition("/")
        self.account = host.split(".", 1)[0]
        self.prefix = path.strip("/")
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import ContainerClient

        self.client = ContainerClient(
            account_url=f"https://{self.account}.blob.core.windows.net",
            container_name=container,
            credential=DefaultAzureCredential(exclude_interactive_browser_credential=True),
        )

    def _key(self, name: str) -> str:
        return f"{self.prefix}/{name}" if self.prefix else name

    def read(self, name: str) -> str | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self.client.download_blob(self._key(name)).readall().decode("utf-8")
        except ResourceNotFoundError:
            return None

    def write(self, name: str, text: str) -> None:
        self.client.upload_blob(self._key(name), text.encode("utf-8"), overwrite=True)

    def list(self, prefix: str) -> list[str]:
        start = len(self.prefix) + 1 if self.prefix else 0
        return sorted(
            b.name[start:] for b in self.client.list_blobs(name_starts_with=self._key(prefix))
        )


def target_for(location: str) -> Target:
    if location.startswith("abfss://"):
        return AdlsTarget(location)
    return LocalTarget(location.removeprefix("file://"))


def run_id(report: Report) -> str:
    return report.generated_at.strftime("%Y%m%dT%H%M%SZ")


def _text(finding: Finding) -> tuple[str, str]:
    evidence = "\n".join(
        f"{e.source}: {e.signal}"
        + (f" ({e.observed_at.date().isoformat()})" if e.observed_at else "")
        for e in finding.evidence
    )
    return evidence, "\n".join(finding.coverage_notes)


def _row(report: Report, finding: Finding, status: str) -> dict:
    evidence, notes = _text(finding)
    return {
        "run_id": run_id(report),
        "generated_at": report.generated_at.isoformat(),
        "reference_date": report.reference_date.isoformat(),
        "window_days": report.window_days,
        "status": status,
        "id": finding.id,
        "reading": finding.reading,
        "kind": finding.kind,
        "asset": finding.asset,
        "owner": finding.owner,
        "size_bytes": finding.size_bytes,
        "monthly_cost": finding.monthly_cost if status != "resolved" else None,
        "currency": finding.currency,
        "confidence": finding.confidence,
        "recommendation": finding.recommendation,
        "evidence": evidence,
        "coverage_notes": notes,
        "proof_hash": finding.proof_hash,
    }


def previous_report(target: Target) -> Report | None:
    reports = [name for name in target.list("runs/") if name.endswith("/report.json")]
    if not reports:
        return None
    text = target.read(reports[-1])
    return Report.model_validate_json(text) if text else None


def publish(report: Report, target: Target) -> dict[str, int]:
    """Writes the run and returns counts per status."""
    previous = previous_report(target)
    status = {f.id: "new" for f in report.findings}
    resolved: list[Finding] = []
    if previous is not None:
        changes = diff(previous, report)
        status.update({fid: "ongoing" for fid in changes["ongoing"]})
        old = {f.id: f for f in previous.findings}
        resolved = [old[fid] for fid in changes["resolved"]]
    rows = [_row(report, f, status[f.id]) for f in report.findings]
    rows += [_row(report, f, "resolved") for f in resolved]
    rid = run_id(report)
    target.write(f"runs/{rid}/report.json", report.model_dump_json(indent=2))
    target.write(f"findings/{rid}.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
    counts = {"new": 0, "ongoing": 0, "resolved": 0}
    for r in rows:
        counts[r["status"]] += 1
    costs = report.totals()["monthly_cost"]
    summary = {
        "run_id": rid,
        "generated_at": report.generated_at.isoformat(),
        "reference_date": report.reference_date.isoformat(),
        "window_days": report.window_days,
        "open_findings": len(report.findings),
        "new_findings": counts["new"],
        "ongoing_findings": counts["ongoing"],
        "resolved_findings": counts["resolved"],
        # One currency per row; costs in other currencies stay in the full report.
        "monthly_cost": next(iter(costs.values()), None),
        "currency": next(iter(costs), None),
        "storage_files": report.storage_files,
        "coverage_notes": "\n".join(report.coverage_notes),
    }
    target.write(f"summaries/{rid}.json", json.dumps(summary) + "\n")
    return counts
