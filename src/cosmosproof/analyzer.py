"""Crosses Unity Catalog activity with ADLS inventory and turns silence into findings with proof.

A finding is never "unused" on a single missing signal: lineage only records the events it can
infer, and last access time only exists after it is enabled. Every verdict carries the signals
that support it, a confidence level and notes on what could not be seen.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from cosmos_semantic.bootstrap import _sensitivity

from cosmosproof.config import Rates, StorageConfig
from cosmosproof.federation import FederationSnapshot
from cosmosproof.inventory import Blob, container_url
from cosmosproof.model import Evidence, Finding, finding_id
from cosmosproof.producers import ProducerActivity
from cosmosproof.unity_catalog import LINEAGE_HISTORY_DAYS, CatalogSnapshot, TableInfo

LINEAGE = "system.access.table_lineage"
INFO_SCHEMA = "system.information_schema"
INVENTORY = "Azure Blob Inventory"
LOGS = "Azure Storage resource logs"
LOGS_NOTE = (
    "Storage read logs record every read of a data file, by Databricks or any other tool; "
    "platform maintenance that reads files (for example OPTIMIZE) counts as a read too."
)
GB = 1024**3
# Early-deletion periods per access tier (days), so a recommendation never costs more than it saves.
MIN_RETENTION = {"cool": 30, "cold": 90, "archive": 180}

LINEAGE_MISSING = (
    "Lineage is unavailable (reading system.access needs a grant from a Databricks account "
    "admin), so this verdict rests on storage reads alone. Queries answered by the Databricks "
    "SQL result cache or disk cache do not read storage and are invisible here."
)
DATA_FILES_ONLY = (
    "Only data files count as reads: Delta writers also read _delta_log, and a query answered "
    "from Delta statistics alone (for example COUNT(*)) touches no data file."
)
LINEAGE_PARTIAL = (
    "Unity Catalog lineage records only the reads it can infer; a table with no lineage event "
    "may still be read in ways lineage does not capture (for example plain JDBC or tools "
    "outside Databricks)."
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _norm(path: str) -> str:
    scheme, sep, rest = path.partition("://")
    if not sep:
        return path.rstrip("/")
    host, slash, tail = rest.partition("/")
    return f"{scheme.lower()}://{host.lower()}{slash}{tail}".rstrip("/")


def _is_log(url: str) -> bool:
    return "/_delta_log/" in url


def _gb(size: int) -> str:
    return f"{size / GB:,.2f} GB"


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


@dataclass
class _Group:
    blobs: list[Blob] = field(default_factory=list)
    storage: StorageConfig | None = None

    @property
    def size(self) -> int:
        return sum(b.size for b in self.blobs)

    def last_access(self) -> datetime | None:
        """Last read of a data file. Delta writers also read `_delta_log`, so log files would
        make a table that is only written look read."""
        values = [_utc(b.last_access) for b in self.blobs if b.last_access and not _is_log(b.url)]
        return max(values) if values else None

    def last_log_read(self) -> datetime | None:
        values = [_utc(b.log_read) for b in self.blobs if b.log_read and not _is_log(b.url)]
        return max(values) if values else None

    def has_delta_log(self) -> bool:
        return any(_is_log(b.url) for b in self.blobs)

    def last_modified(self) -> datetime | None:
        values = [_utc(b.last_modified) for b in self.blobs if b.last_modified]
        return max(values) if values else None

    def tiers(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for b in self.blobs:
            out[(b.tier or "unknown").lower()] += b.size
        return dict(out)


class Analyzer:
    def __init__(
        self,
        snapshot: CatalogSnapshot,
        blobs_by_storage: list[tuple[StorageConfig, list[Blob]]],
        *,
        reference: date,
        window_days: int,
        rates: Rates | None = None,
        orphan_depth: int = 2,
        producers: ProducerActivity | None = None,
        federation: FederationSnapshot | None = None,
        price_discount: float = 0.0,
        window_hours: float | None = None,
        now: datetime | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.storages = blobs_by_storage
        self.reference = reference
        self.window_days = window_days
        self.rates = rates
        self.orphan_depth = orphan_depth
        self.producers = producers
        self.federation = federation
        self.price_discount = price_discount
        self.window_hours = window_hours
        if window_hours:
            self.end = _utc(now) or datetime.now(UTC)
            self.cutoff = self.end - timedelta(hours=window_hours)
            self.window_days = round(window_hours / 24, 4)
        else:
            self.end = datetime.combine(reference, time.max, tzinfo=UTC)
            self.cutoff = datetime.combine(
                reference - timedelta(days=window_days), time.min, tzinfo=UTC
            )
        self.notes: list[str] = []

    # --- public -------------------------------------------------------------------------

    def run(self) -> list[Finding]:
        findings: list[Finding] = []
        table_groups, orphans = self._assign_blobs()
        path_reads = {_norm(p): _utc(t) for p, t in self.snapshot.activity.path_reads.items()}
        self._global_notes()
        for table in self.snapshot.tables:
            if table.ignored or table.table_type.upper() in {
                "VIEW",
                "MATERIALIZED_VIEW",
                "METRIC_VIEW",
            }:
                continue
            group = table_groups.get(table.full_name, _Group())
            found = self._table_findings(table, group, path_reads)
            findings.extend(found)
        for prefix, group in sorted(orphans.items()):
            orphan = self._orphan_finding(prefix, group, path_reads)
            if orphan:
                findings.append(orphan)
        if self.producers is not None:
            findings.extend(self._producer_findings())
        if self.federation is not None:
            findings.extend(self._connection_findings())
        findings.sort(key=lambda f: (-(f.monthly_cost or 0), -f.size_bytes, f.asset))
        return [f.seal() for f in findings]

    # --- blob assignment ----------------------------------------------------------------

    def _assign_blobs(self) -> tuple[dict[str, _Group], dict[str, _Group]]:
        locations = sorted(
            ((_norm(t.storage_path), t.full_name) for t in self.snapshot.tables if t.storage_path),
            key=lambda item: -len(item[0]),
        )
        table_groups: dict[str, _Group] = defaultdict(_Group)
        orphans: dict[str, _Group] = defaultdict(_Group)
        for storage, blobs in self.storages:
            base = _norm(container_url(storage.account, storage.container))
            # Orphan Delta tables are grouped by their root (the folder holding _delta_log), so
            # two dropped tables side by side are judged separately.
            delta_roots = sorted(
                {_norm(b.url).split("/_delta_log/", 1)[0] for b in blobs if _is_log(b.url)},
                key=len,
                reverse=True,
            )
            for blob in blobs:
                url = _norm(blob.url)
                owner = next((name for loc, name in locations if _under(url, loc)), None)
                if owner:
                    group = table_groups[owner]
                elif root := next((r for r in delta_roots if _under(url, r)), None):
                    group = orphans[root]
                else:
                    relative = url[len(base) + 1 :].split("/")
                    depth = min(self.orphan_depth, max(len(relative) - 1, 1))
                    group = orphans[base + "/" + "/".join(relative[:depth])]
                group.storage = storage
                group.blobs.append(blob)
        return table_groups, orphans

    # --- signals ------------------------------------------------------------------------

    def _global_notes(self) -> None:
        if not self.snapshot.activity.lineage_available:
            self.notes.append(
                "Storage-only mode: lineage, jobs and pipelines are unavailable because the "
                "identity cannot read system.access (that grant needs a Databricks account "
                "admin). Findings rest on ADLS last access times, none is above medium "
                "confidence, and storage without last access evidence is not judged."
            )
            return
        earliest = _utc(self.snapshot.activity.earliest_event)
        if self.window_days > LINEAGE_HISTORY_DAYS:
            self.notes.append(
                f"The window ({self.window_days} days) is longer than the lineage history "
                f"(about {LINEAGE_HISTORY_DAYS} days); older reads cannot be seen."
            )
        if earliest is None:
            self.notes.append("No lineage events were found at all; check system table grants.")
        elif earliest > self.cutoff:
            self.notes.append(
                f"Lineage history starts on {earliest.date().isoformat()}, after the window "
                "start; reads before that date cannot be seen."
            )

    def _window_label(self) -> str:
        return f"{self.window_hours:g}-hour" if self.window_hours else f"{self.window_days}-day"

    def _span_label(self) -> str:
        return f"{self.window_hours:g} hours" if self.window_hours else f"{self.window_days} days"

    def _logs_cover_window(self, storage: StorageConfig | None) -> bool:
        return bool(
            storage and storage.access_logs and _utc(storage.access_logs.since) <= self.cutoff
        )

    def _access_covers_window(self, storage: StorageConfig | None) -> bool:
        return bool(
            storage
            and storage.access_tracking_since
            and datetime.combine(storage.access_tracking_since, time.min, tzinfo=UTC) <= self.cutoff
        )

    def _cost(self, group: _Group) -> tuple[float | None, str | None]:
        if not self.rates or not self.rates.per_gb_month or not group.blobs:
            return None, None
        prices = {k.lower(): v for k, v in self.rates.per_gb_month.items()}
        total = 0.0
        for tier, size in group.tiers().items():
            if tier not in prices:
                return None, None
            total += size / GB * prices[tier]
        return round(total, 2), self.rates.currency

    def _storage_evidence(self, group: _Group, notes: list[str]) -> tuple[list[Evidence], str]:
        """Returns the storage evidence and the storage verdict: read, silent or unknown."""
        if not group.blobs:
            return [], "unknown"
        evidence = [
            Evidence(
                source=INVENTORY,
                signal=f"{len(group.blobs)} files, {_gb(group.size)}, by tier: "
                + ", ".join(f"{tier} {_gb(size)}" for tier, size in sorted(group.tiers().items())),
                observed_at=group.last_modified(),
            )
        ]
        tracking = self._access_covers_window(group.storage)
        logs = self._logs_cover_window(group.storage)
        if not tracking and not logs:
            notes.append(
                "Neither last access time tracking nor storage read logs cover the whole window, "
                "so storage reads cannot confirm or refute the lineage signal."
            )
            return evidence, "unknown"
        if group.has_delta_log():
            notes.append(DATA_FILES_ONLY)
        if logs:
            notes.append(LOGS_NOTE)
        last = group.last_access() if tracking else None
        logged = group.last_log_read() if logs else None
        if last and last >= self.cutoff:
            evidence.append(
                Evidence(source=INVENTORY, signal="file read inside the window", observed_at=last)
            )
            return evidence, "read"
        if logged and logged >= self.cutoff:
            evidence.append(
                Evidence(source=LOGS, signal="data file read inside the window", observed_at=logged)
            )
            return evidence, "read"
        if tracking:
            evidence.append(
                Evidence(
                    source=INVENTORY,
                    signal=(
                        "no file read inside the window"
                        + (
                            f"; last read {last.date().isoformat()}"
                            if last
                            else "; never read since tracking began"
                        )
                    ),
                    observed_at=last,
                )
            )
        if logs:
            evidence.append(
                Evidence(
                    source=LOGS,
                    signal=(
                        "no data file read in the storage read logs inside the window"
                        + (f"; last logged read {logged.isoformat()}" if logged else "")
                    ),
                    observed_at=logged,
                )
            )
        return evidence, "silent"

    def _tier_advice(self, group: _Group) -> str:
        hot = group.tiers().get("hot", 0)
        if not hot:
            return ""
        return (
            " Moving it from Hot to Cool or Cold cuts storage cost while keeping it online; "
            "mind the early-deletion periods (Cool 30 days, Cold 90, Archive 180)."
        )

    # --- findings -----------------------------------------------------------------------

    def _table_findings(
        self, table: TableInfo, group: _Group, path_reads: dict[str, datetime | None]
    ) -> list[Finding]:
        created = _utc(table.created)
        if created and created > self.cutoff:
            return []
        activity = self.snapshot.activity
        lineage = activity.lineage_available
        last_read = self._last_read(table.full_name) if lineage else None
        if lineage and table.storage_path:
            location = _norm(table.storage_path)
            path_hits = [t for p, t in path_reads.items() if t and _under(p, location)]
            if path_hits:
                newest = max(path_hits)
                last_read = max(last_read, newest) if last_read else newest
        if last_read and last_read >= self.cutoff:
            return []

        notes = [LINEAGE_PARTIAL] if lineage else [LINEAGE_MISSING]
        evidence = (
            [
                Evidence(
                    source=LINEAGE,
                    signal=(
                        f"no read inside the {self._window_label()} window; last read "
                        f"{last_read.date().isoformat()}"
                        if last_read
                        else "no read recorded in the lineage history"
                    ),
                    observed_at=last_read,
                )
            ]
            if lineage
            else []
        )
        last_write = _utc(activity.table_writes.get(table.full_name))
        if last_write:
            evidence.append(
                Evidence(
                    source=LINEAGE, signal="last write (still being fed)", observed_at=last_write
                )
            )
        storage_evidence, storage_verdict = self._storage_evidence(group, notes)
        if storage_verdict == "read" or (not lineage and storage_verdict != "silent"):
            return []
        evidence.extend(storage_evidence)
        confidence = "high" if lineage and storage_verdict == "silent" else "medium"
        cost, currency = self._cost(group)
        if group.blobs and cost is None:
            notes.append("No storage rates configured for every tier, so no cost estimate.")
        if not group.blobs:
            notes.append(
                "No inventory covers this table's storage, so its size and cost are unknown."
            )

        fed = bool(last_write and last_write >= self.cutoff)
        recommendation = (
            "Nobody reads this table but something still writes to it: find the pipeline that "
            "feeds it and confirm with the owner whether it can stop."
            if fed
            else "Confirm with the owner that this table is no longer needed before archiving or dropping it."
        ) + self._tier_advice(group)

        details = {
            "table_type": table.table_type,
            "format": table.data_source_format,
            "storage_path": table.storage_path,
            "last_read": last_read.isoformat() if last_read else None,
            "last_write": last_write.isoformat() if last_write else None,
            "still_fed": fed,
        }
        feeders = self._feeders(table.full_name)
        if feeders:
            details["fed_by"] = feeders
        findings = [
            Finding(
                id=finding_id("unused_table", table.full_name),
                reading="cost",
                kind="unused_table",
                asset=table.full_name,
                owner=table.owner,
                size_bytes=group.size,
                monthly_cost=cost,
                currency=currency,
                confidence=confidence,
                evidence=evidence,
                coverage_notes=notes,
                recommendation=recommendation,
                details=details,
                window_days=self.window_days,
                reference_date=self.reference,
            )
        ]

        personal = {
            c: level
            for c in table.columns
            if (level := _sensitivity(c.lower(), table.full_name.split(".")[-1].lower()))
        }
        if personal:
            findings.append(
                Finding(
                    id=finding_id("unused_personal_data", table.full_name),
                    reading="compliance",
                    kind="unused_personal_data",
                    asset=table.full_name,
                    owner=table.owner,
                    size_bytes=group.size,
                    confidence=confidence,
                    evidence=[
                        *evidence,
                        Evidence(
                            source=f"{INFO_SCHEMA}.columns",
                            signal="columns that usually hold personal data: "
                            + ", ".join(f"{c} ({lvl})" for c, lvl in sorted(personal.items())),
                        ),
                    ],
                    coverage_notes=[
                        *notes,
                        "Personal data is detected by column name only; a person must confirm "
                        "the content before acting.",
                    ],
                    recommendation=(
                        "Personal data kept with no purpose in use conflicts with the LGPD "
                        "necessity principle. Ask the owner and the DPO whether it must be "
                        "retained, anonymized or deleted."
                    ),
                    details={"personal_columns": personal, **details},
                    window_days=self.window_days,
                    reference_date=self.reference,
                )
            )
        return findings

    def _orphan_finding(
        self, prefix: str, group: _Group, path_reads: dict[str, datetime | None]
    ) -> Finding | None:
        modified = group.last_modified()
        if modified and modified > self.cutoff:
            return None
        hits = [t for p, t in path_reads.items() if t and (_under(p, prefix) or _under(prefix, p))]
        last_path_read = max(hits) if hits else None
        if last_path_read and last_path_read >= self.cutoff:
            return None
        lineage = self.snapshot.activity.lineage_available
        notes = [
            "No Unity Catalog table owns this storage, so readers outside Databricks are invisible "
            "to lineage."
            if lineage
            else LINEAGE_MISSING
        ]
        evidence = (
            [
                Evidence(
                    source=LINEAGE,
                    signal=(
                        f"no path read inside the window; last path read {last_path_read.date().isoformat()}"
                        if last_path_read
                        else "no path read recorded in the lineage history"
                    ),
                    observed_at=last_path_read,
                )
            ]
            if lineage
            else []
        )
        storage_evidence, verdict = self._storage_evidence(group, notes)
        if verdict == "read" or (not lineage and verdict != "silent"):
            return None
        evidence.extend(storage_evidence)
        cost, currency = self._cost(group)
        return Finding(
            id=finding_id("orphan_path", prefix),
            reading="cost",
            kind="orphan_path",
            asset=prefix,
            size_bytes=group.size,
            monthly_cost=cost,
            currency=currency,
            confidence="medium" if verdict == "silent" else "low",
            evidence=evidence,
            coverage_notes=notes,
            recommendation=(
                "Storage that no table owns and nobody reads. Identify who wrote it (last "
                "modified date, folder name) before archiving it." + self._tier_advice(group)
            ),
            details={"files": len(group.blobs), "tiers": group.tiers()},
            window_days=self.window_days,
            reference_date=self.reference,
        )

    # --- producers (phase 2) ------------------------------------------------------------

    def _producer_label(self, key: str) -> str:
        kind, _, ident = key.partition(":")
        meta = self.producers.producers.get(key) if self.producers else None
        return f"{kind} {ident}" + (f" ({meta.name})" if meta and meta.name else "")

    def _recent_outputs(self, key: str) -> dict[str, datetime]:
        assert self.producers is not None
        known = {t.full_name for t in self.snapshot.tables if not t.ignored}
        return {
            table: last
            for table, raw in self.producers.writes.get(key, {}).items()
            if table in known and (last := _utc(raw)) and last >= self.cutoff
        }

    def _reads_excluding(self, table: str, ignored: set[str]) -> list[datetime]:
        assert self.producers is not None
        return [
            read
            for entity, raw in self.producers.reads_by.get(table, {}).items()
            if entity not in ignored and (read := _utc(raw))
        ]

    def _dead_producers(self) -> set[str]:
        """Producers whose recent outputs nobody uses. A read by a dead producer is not use
        either, so the set grows until it is stable: job B reading A's table only to feed
        tables nobody reads does not keep A alive."""
        if self.producers is None:
            return set()
        if hasattr(self, "_dead"):
            return self._dead
        dead: set[str] = set()
        changed = True
        while changed:
            changed = False
            for key in self.producers.writes:
                meta = self.producers.producers.get(key)
                if key in dead or (meta and meta.deleted):
                    continue
                outputs = self._recent_outputs(key)
                if not outputs:
                    continue
                ignored = dead | {key}
                if not any(
                    read >= self.cutoff
                    for table in outputs
                    for read in self._reads_excluding(table, ignored)
                ):
                    dead.add(key)
                    changed = True
        self._dead = dead
        return dead

    def _last_read(self, table: str) -> datetime | None:
        """Last read that counts as use. Reads by dead producers do not count; a live
        producer reading its own input still does, so intermediate tables of a used pipeline
        are never flagged."""
        if self.producers is None or table not in self.producers.reads_by:
            return _utc(self.snapshot.activity.table_reads.get(table))
        reads = self._reads_excluding(table, self._dead_producers())
        return max(reads) if reads else None

    def _feeders(self, table: str) -> list[str]:
        if self.producers is None:
            return []
        return sorted(
            self._producer_label(key)
            for key, tables in self.producers.writes.items()
            if (last := _utc(tables.get(table))) and last >= self.cutoff
        )

    def _connection_findings(self) -> list[Finding]:
        assert self.federation is not None
        if not self.snapshot.activity.lineage_available:
            self.notes.append(
                "Federation connections were not judged: queries on foreign catalogs read no "
                "lake storage, so without lineage their use cannot be seen."
            )
            return []
        findings: list[Finding] = []
        reads = {name: _utc(t) for name, t in self.snapshot.activity.table_reads.items() if t}
        for conn in self.federation.connections:
            created = _utc(conn.created)
            if created and created > self.cutoff:
                continue
            if conn.pipelines:
                continue  # an ingestion pipeline uses it; the producer reading judges that
            if not conn.catalogs and not self.federation.pipelines_checked:
                continue  # could be used by an ingestion pipeline we could not see
            hits = [
                t
                for name, t in reads.items()
                if any(name.startswith(f"{c}.") for c in conn.catalogs)
            ]
            last = max(hits) if hits else None
            if last and last >= self.cutoff:
                continue
            what = (
                f"{len(conn.catalogs)} foreign catalog(s): " + ", ".join(conn.catalogs)
                if conn.catalogs
                else "no foreign catalog and no ingestion pipeline"
            )
            evidence = [
                Evidence(
                    source="Unity Catalog connections",
                    signal=(
                        f"{conn.connection_type or 'unknown'} connection to "
                        f"{conn.host or 'an unknown host'} with {conn.credential_type or 'stored'} "
                        f"credentials; {what}"
                    ),
                    observed_at=created,
                ),
                Evidence(
                    source=LINEAGE,
                    signal=(
                        f"no read of any table in its catalogs inside the {self._window_label()} "
                        "window" + (f"; last read {last.date().isoformat()}" if last else "")
                    ),
                    observed_at=last,
                ),
            ]
            findings.append(
                Finding(
                    id=finding_id("unused_connection", conn.name),
                    reading="risk",
                    kind="unused_connection",
                    asset=f"connection {conn.name}",
                    owner=conn.owner,
                    confidence="medium",
                    evidence=evidence,
                    coverage_notes=[
                        LINEAGE_PARTIAL,
                        "The source database may serve other applications; this only says "
                        "Databricks does not use this connection.",
                    ],
                    recommendation=(
                        "A connection nobody uses still holds credentials to a production "
                        "database. Confirm with the owner, then drop it (and its foreign "
                        "catalogs) or at least rotate its credentials."
                    ),
                    details={
                        "connection_type": conn.connection_type,
                        "host": conn.host,
                        "catalogs": conn.catalogs,
                    },
                    window_days=self.window_days,
                    reference_date=self.reference,
                )
            )
        return findings

    def _producer_findings(self) -> list[Finding]:
        assert self.producers is not None
        activity = self.producers
        dead = self._dead_producers()
        findings: list[Finding] = []
        for key in sorted(dead):
            meta = activity.producers.get(key)
            recent = self._recent_outputs(key)
            outside = [read for table in recent for read in self._reads_excluding(table, dead)]
            last_outside = max(outside) if outside else None
            tables = sorted(recent)
            evidence = [
                Evidence(
                    source=LINEAGE,
                    signal=f"wrote {len(tables)} tables inside the window: " + ", ".join(tables),
                    observed_at=max(recent.values()),
                ),
                Evidence(
                    source=LINEAGE,
                    signal=(
                        "inside the window, none of them was read except by this producer or by "
                        "other producers whose outputs nobody uses"
                        + (
                            f"; last other read {last_outside.date().isoformat()}"
                            if last_outside
                            else "; no other read in the lineage history"
                        )
                    ),
                    observed_at=last_outside,
                ),
            ]
            notes = [LINEAGE_PARTIAL]
            cost = activity.costs.get(key)
            monthly = currency = None
            if cost and cost.currency:
                paid = cost.amount * (1 - self.price_discount)
                monthly = round(paid / self.window_days * 30, 2)
                currency = cost.currency
                unit = f" {cost.unit}" if cost.unit else ""
                evidence.append(
                    Evidence(
                        source="system.billing.usage",
                        signal=(
                            f"{cost.quantity:,.2f}{unit} in the last {self._span_label()}, "
                            f"{cost.amount:,.2f} {cost.currency} at list price"
                        ),
                    )
                )
                notes.append(
                    f"Cost applies the configured {self.price_discount:.0%} discount to "
                    "Databricks list prices."
                    if self.price_discount
                    else "Cost uses Databricks list prices; contract discounts are not applied."
                )
            else:
                notes.append("No billing data for this producer, so its cost is unknown.")
            kind_detail = meta.kind_detail if meta else None
            findings.append(
                Finding(
                    id=finding_id("unused_producer", key),
                    reading="cost",
                    kind="unused_producer",
                    asset=self._producer_label(key),
                    owner=meta.owner if meta else None,
                    monthly_cost=monthly,
                    currency=currency,
                    confidence="medium",
                    evidence=evidence,
                    coverage_notes=notes,
                    recommendation=(
                        "This producer keeps running and paying for compute, but nothing outside "
                        "it reads what it writes. Confirm with the owner whether its outputs are "
                        "still needed before pausing its schedule."
                    ),
                    details={
                        "producer": key,
                        "type": kind_detail,
                        "tables": {t: recent[t].isoformat() for t in tables},
                        "window_cost": round(cost.amount, 2) if cost else None,
                    },
                    window_days=self.window_days,
                    reference_date=self.reference,
                )
            )
        return findings
