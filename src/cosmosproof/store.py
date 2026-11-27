"""The audit store: `cosmosproof.audit`, a DuckDB database holding the metric model (ADR 0010).

It is the product's core output. Dashboards (Databricks, Power BI or anything else) are the
customer's choice on top of it, through the Parquet export.

Model:
    dim_resource        workspaces and ADLS accounts discovered, with environment and selection
    dim_run             one row per scan run
    fact_finding        findings per run, with status new / ongoing / resolved
    fact_resource_scan  per run and resource: status, error and volume metrics
    event_log           what happened during each run
    v_* views           ready-made metrics: KPIs, cost by owner and by resource, trend, PII
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from cosmosproof.discovery import Resource
from cosmosproof.model import Finding, Report

FILE_NAME = "cosmosproof.audit"
SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR);
CREATE TABLE IF NOT EXISTS dim_resource (
    resource_id VARCHAR PRIMARY KEY, kind VARCHAR, name VARCHAR, subscription VARCHAR,
    resource_group VARCHAR, location VARCHAR, tags JSON, environment VARCHAR,
    environment_source VARCHAR, host VARCHAR, selected BOOLEAN, status VARCHAR, error VARCHAR,
    warehouses JSON, catalogs JSON, locations JSON, first_seen TIMESTAMPTZ, last_seen TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS dim_run (
    run_id VARCHAR PRIMARY KEY, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
    tool_version VARCHAR, window_days DOUBLE, resources_scanned INTEGER,
    resources_failed INTEGER, open_findings INTEGER, new_findings INTEGER,
    resolved_findings INTEGER
);
CREATE TABLE IF NOT EXISTS fact_finding (
    run_id VARCHAR, finding_id VARCHAR, resource_id VARCHAR, status VARCHAR, reading VARCHAR,
    kind VARCHAR, asset VARCHAR, owner VARCHAR, confidence VARCHAR, size_bytes BIGINT,
    monthly_cost DOUBLE, currency VARCHAR, recommendation VARCHAR, evidence JSON,
    coverage_notes JSON, proof_hash VARCHAR, reference_date DATE, window_days DOUBLE,
    PRIMARY KEY (run_id, finding_id)
);
CREATE TABLE IF NOT EXISTS fact_resource_scan (
    run_id VARCHAR, resource_id VARCHAR, status VARCHAR, error VARCHAR, mode VARCHAR,
    tables_seen INTEGER, files_seen BIGINT, findings INTEGER, unused_bytes BIGINT,
    coverage_notes JSON, PRIMARY KEY (run_id, resource_id)
);
CREATE TABLE IF NOT EXISTS event_log (
    logged_at TIMESTAMPTZ, run_id VARCHAR, resource_id VARCHAR, level VARCHAR, message VARCHAR
);
"""

VIEWS = """
CREATE OR REPLACE VIEW v_latest_run AS
    SELECT * FROM dim_run ORDER BY started_at DESC LIMIT 1;
CREATE OR REPLACE VIEW v_open_findings AS
    SELECT f.*, r.name AS resource_name, r.environment
    FROM fact_finding f
    LEFT JOIN dim_resource r USING (resource_id)
    WHERE f.run_id = (SELECT run_id FROM v_latest_run) AND f.status <> 'resolved';
CREATE OR REPLACE VIEW v_kpis AS
    SELECT
        (SELECT run_id FROM v_latest_run) AS run_id,
        COUNT(*) AS open_findings,
        COUNT(*) FILTER (WHERE status = 'new') AS new_findings,
        (SELECT COUNT(*) FROM fact_finding
          WHERE run_id = (SELECT run_id FROM v_latest_run) AND status = 'resolved')
          AS resolved_findings,
        COUNT(*) FILTER (WHERE reading = 'cost') AS cost_findings,
        COUNT(*) FILTER (WHERE reading = 'risk') AS risk_findings,
        COUNT(*) FILTER (WHERE reading = 'compliance') AS pii_findings,
        CAST(SUM(size_bytes) FILTER (WHERE reading = 'cost') AS BIGINT) AS unused_bytes,
        SUM(monthly_cost) AS monthly_cost,
        ANY_VALUE(currency) FILTER (WHERE monthly_cost IS NOT NULL) AS currency
    FROM v_open_findings;
CREATE OR REPLACE VIEW v_cost_by_owner AS
    SELECT COALESCE(owner, 'unknown') AS owner, COUNT(*) AS findings,
           SUM(monthly_cost) AS monthly_cost, ANY_VALUE(currency) FILTER (WHERE monthly_cost IS NOT NULL) AS currency,
           CAST(SUM(size_bytes) FILTER (WHERE reading = 'cost') AS BIGINT) AS unused_bytes
    FROM v_open_findings GROUP BY 1 ORDER BY monthly_cost DESC NULLS LAST, findings DESC;
CREATE OR REPLACE VIEW v_cost_by_resource AS
    SELECT resource_id, resource_name, environment, COUNT(*) AS findings,
           SUM(monthly_cost) AS monthly_cost, ANY_VALUE(currency) FILTER (WHERE monthly_cost IS NOT NULL) AS currency,
           CAST(SUM(size_bytes) FILTER (WHERE reading = 'cost') AS BIGINT) AS unused_bytes
    FROM v_open_findings GROUP BY 1, 2, 3 ORDER BY monthly_cost DESC NULLS LAST, findings DESC;
CREATE OR REPLACE VIEW v_trend AS
    SELECT r.run_id, r.started_at, r.open_findings, r.new_findings, r.resolved_findings,
           SUM(f.monthly_cost) FILTER (WHERE f.status <> 'resolved') AS monthly_cost,
           CAST(SUM(f.size_bytes) FILTER (WHERE f.status <> 'resolved' AND f.reading = 'cost')
                AS BIGINT) AS unused_bytes
    FROM dim_run r LEFT JOIN fact_finding f USING (run_id)
    GROUP BY ALL ORDER BY r.started_at;
CREATE OR REPLACE VIEW v_pii_at_rest AS
    SELECT resource_name, asset, owner, confidence, size_bytes, evidence, proof_hash
    FROM v_open_findings WHERE reading = 'compliance';
CREATE OR REPLACE VIEW v_resource_health AS
    SELECT r.resource_id, r.kind, r.name, r.environment, r.selected, r.status AS discovery_status,
           s.status AS last_scan_status, s.error AS last_scan_error, s.mode, s.tables_seen,
           s.files_seen, s.findings
    FROM dim_resource r
    LEFT JOIN fact_resource_scan s
      ON s.resource_id = r.resource_id AND s.run_id = (SELECT run_id FROM v_latest_run);
"""

EXPORT = [
    "dim_resource",
    "dim_run",
    "fact_finding",
    "fact_resource_scan",
    "event_log",
    "v_kpis",
    "v_cost_by_owner",
    "v_cost_by_resource",
    "v_trend",
    "v_pii_at_rest",
    "v_resource_health",
]


class AuditStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.con = duckdb.connect(str(self.path))
        self.con.execute(DDL)
        # Additive migrations for stores created by earlier versions.
        self.con.execute("ALTER TABLE dim_resource ADD COLUMN IF NOT EXISTS managed_by VARCHAR")
        self.con.execute(
            "INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", [str(SCHEMA_VERSION)]
        )
        self.con.execute(VIEWS)

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> AuditStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- resources -----------------------------------------------------------------------

    def upsert_resources(self, resources: list[Resource], selection: dict[str, bool]) -> None:
        now = datetime.now(UTC)
        for r in resources:
            self.con.execute(
                """
                INSERT INTO dim_resource (
                    resource_id, kind, name, subscription, resource_group, location, tags,
                    environment, environment_source, host, selected, status, error, warehouses,
                    catalogs, locations, first_seen, last_seen, managed_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (resource_id) DO UPDATE SET managed_by = excluded.managed_by,
                    kind = excluded.kind, name = excluded.name, subscription = excluded.subscription,
                    resource_group = excluded.resource_group, location = excluded.location,
                    tags = excluded.tags, environment = excluded.environment,
                    environment_source = excluded.environment_source, host = excluded.host,
                    selected = excluded.selected, status = excluded.status, error = excluded.error,
                    warehouses = excluded.warehouses, catalogs = excluded.catalogs,
                    locations = excluded.locations, last_seen = excluded.last_seen
                """,
                [
                    r.id, r.kind, r.name, r.subscription, r.resource_group, r.location,
                    json.dumps(r.tags), r.environment, r.environment_source, r.host,
                    selection.get(r.id, False), r.status, r.error, json.dumps(r.warehouses),
                    json.dumps(r.catalogs), json.dumps(r.locations), now, now, r.managed_by,
                ],
            )  # fmt: skip

    def resources(self) -> list[dict]:
        cur = self.con.execute("SELECT * FROM dim_resource ORDER BY kind, name")
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]

    # --- runs ----------------------------------------------------------------------------

    def previous_open(self, before_run: str) -> dict[str, dict]:
        row = self.con.execute(
            "SELECT run_id FROM dim_run WHERE run_id < ? ORDER BY run_id DESC LIMIT 1",
            [before_run],
        ).fetchone()
        if not row:
            return {}
        cur = self.con.execute(
            "SELECT * FROM fact_finding WHERE run_id = ? AND status <> 'resolved'", [row[0]]
        )
        names = [d[0] for d in cur.description]
        return {r[1]: dict(zip(names, r, strict=True)) for r in cur.fetchall()}

    def log(self, run_id: str, level: str, message: str, resource_id: str | None = None) -> None:
        self.con.execute(
            "INSERT INTO event_log VALUES (?, ?, ?, ?, ?)",
            [datetime.now(UTC), run_id, resource_id, level, message],
        )

    def record_resource_scan(
        self,
        run_id: str,
        resource_id: str,
        *,
        status: str,
        error: str | None = None,
        report: Report | None = None,
        tables_seen: int = 0,
    ) -> None:
        mode = None
        findings = unused = 0
        notes: list[str] = []
        if report is not None:
            mode = (
                "storage-only"
                if any("Storage-only mode" in n for n in report.coverage_notes)
                else "lineage"
            )
            findings = len(report.findings)
            unused = report.totals()["unused_bytes"]
            notes = report.coverage_notes
        self.con.execute(
            "INSERT OR REPLACE INTO fact_resource_scan VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id, resource_id, status, error, mode, tables_seen,
                report.storage_files if report else 0, findings, unused, json.dumps(notes),
            ],
        )  # fmt: skip

    def record_run(
        self,
        run_id: str,
        started_at: datetime,
        tool_version: str,
        window_days: float,
        findings: list[tuple[str, Finding]],
        resources_scanned: int,
        resources_failed: int,
        judged: set[str] | None = None,
    ) -> dict[str, int]:
        """Stores the findings of a run (each with the workspace it came from), marks them new
        or ongoing against the previous run, and adds the resolved ones."""
        previous = self.previous_open(run_id)
        seen: set[str] = set()
        counts = {"new": 0, "ongoing": 0, "resolved": 0}
        for resource_id, f in findings:
            if f.id in seen:  # two workspaces on one metastore see the same tables
                continue
            seen.add(f.id)
            status = "ongoing" if f.id in previous else "new"
            counts[status] += 1
            self._insert_finding(run_id, resource_id, f, status)
        for fid, old in previous.items():
            if fid in seen:
                continue
            if judged is not None and old["resource_id"] not in judged:
                # Not verified this run (failed, or nothing visible): keep it open.
                seen.add(fid)
                counts["ongoing"] += 1
                self.con.execute(
                    "INSERT INTO fact_finding SELECT ? AS run_id, * EXCLUDE (run_id) "
                    "REPLACE ('ongoing' AS status) FROM fact_finding "
                    "WHERE run_id = ? AND finding_id = ?",
                    [run_id, old["run_id"], fid],
                )
                continue
            if fid not in seen:
                counts["resolved"] += 1
                self.con.execute(
                    "INSERT INTO fact_finding SELECT ? AS run_id, finding_id, resource_id, "
                    "'resolved', reading, kind, asset, owner, confidence, size_bytes, NULL, "
                    "currency, recommendation, evidence, coverage_notes, proof_hash, "
                    "reference_date, window_days FROM fact_finding WHERE run_id = ? AND finding_id = ?",
                    [run_id, old["run_id"], fid],
                )
        self.con.execute(
            "INSERT OR REPLACE INTO dim_run VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id, started_at, datetime.now(UTC), tool_version, window_days,
                resources_scanned, resources_failed, counts["new"] + counts["ongoing"],
                counts["new"], counts["resolved"],
            ],
        )  # fmt: skip
        return counts

    def _insert_finding(self, run_id: str, resource_id: str, f: Finding, status: str) -> None:
        evidence = [e.model_dump(mode="json") for e in f.evidence]
        self.con.execute(
            "INSERT OR REPLACE INTO fact_finding VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id, f.id, resource_id, status, f.reading, f.kind, f.asset, f.owner,
                f.confidence, f.size_bytes, f.monthly_cost, f.currency, f.recommendation,
                json.dumps(evidence), json.dumps(f.coverage_notes), f.proof_hash,
                f.reference_date, f.window_days,
            ],
        )  # fmt: skip

    # --- metrics and export -------------------------------------------------------------

    def kpis(self) -> dict:
        cur = self.con.execute("SELECT * FROM v_kpis")
        names = [d[0] for d in cur.description]
        row = cur.fetchone()
        return dict(zip(names, row, strict=True)) if row else {}

    def export_parquet(self, folder: str | Path) -> list[Path]:
        """One Parquet file per table and metric view: the interface for any BI tool."""
        out = Path(folder)
        out.mkdir(parents=True, exist_ok=True)
        files = []
        for name in EXPORT:
            path = out / f"{name}.parquet"
            self.con.execute(f"COPY (SELECT * FROM {name}) TO '{path.as_posix()}' (FORMAT parquet)")
            files.append(path)
        return files
