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
from cosmosproof.inventory import Blob, container_url
from cosmosproof.model import Evidence, Finding, finding_id
from cosmosproof.producers import ProducerActivity
from cosmosproof.unity_catalog import LINEAGE_HISTORY_DAYS, CatalogSnapshot, TableInfo

LINEAGE = "system.access.table_lineage"
INFO_SCHEMA = "system.information_schema"
INVENTORY = "Azure Blob Inventory"
GB = 1024**3
# Early-deletion periods per access tier (days), so a recommendation never costs more than it saves.
MIN_RETENTION = {"cool": 30, "cold": 90, "archive": 180}

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
        values = [_utc(b.last_access) for b in self.blobs if b.last_access]
        return max(values) if values else None

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
    ) -> None:
        self.snapshot = snapshot
        self.storages = blobs_by_storage
        self.reference = reference
        self.window_days = window_days
        self.rates = rates
        self.orphan_depth = orphan_depth
        self.producers = producers
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
            if table.table_type.upper() in {"VIEW", "MATERIALIZED_VIEW", "METRIC_VIEW"}:
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
            for blob in blobs:
                url = _norm(blob.url)
                owner = next((name for loc, name in locations if _under(url, loc)), None)
                if owner:
                    group = table_groups[owner]
                else:
                    relative = url[len(base) + 1 :].split("/")
                    depth = min(self.orphan_depth, max(len(relative) - 1, 1))
                    group = orphans[base + "/" + "/".join(relative[:depth])]
                group.storage = storage
                group.blobs.append(blob)
        return table_groups, orphans

    # --- signals ------------------------------------------------------------------------

    def _global_notes(self) -> None:
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
        if not self._access_covers_window(group.storage):
            notes.append(
                "Last access time tracking is off or was enabled after the window start, so "
                "storage reads cannot confirm or refute the lineage signal."
            )
            return evidence, "unknown"
        last = group.last_access()
        if last and last >= self.cutoff:
            evidence.append(
                Evidence(source=INVENTORY, signal="file read inside the window", observed_at=last)
            )
            return evidence, "read"
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
        last_read = self._last_read(table.full_name)
        if table.storage_path:
            location = _norm(table.storage_path)
            path_hits = [t for p, t in path_reads.items() if t and _under(p, location)]
            if path_hits:
                newest = max(path_hits)
                last_read = max(last_read, newest) if last_read else newest
        if last_read and last_read >= self.cutoff:
            return []

        notes = [LINEAGE_PARTIAL]
        evidence = [
            Evidence(
                source=LINEAGE,
                signal=(
                    f"no read inside the {self.window_days}-day window; last read "
                    f"{last_read.date().isoformat()}"
                    if last_read
                    else "no read recorded in the lineage history"
                ),
                observed_at=last_read,
            )
        ]
        last_write = _utc(activity.table_writes.get(table.full_name))
        if last_write:
            evidence.append(
                Evidence(
                    source=LINEAGE, signal="last write (still being fed)", observed_at=last_write
                )
            )
        storage_evidence, storage_verdict = self._storage_evidence(group, notes)
        if storage_verdict == "read":
            return []
        evidence.extend(storage_evidence)
        confidence = "high" if storage_verdict == "silent" else "medium"
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
        notes = [
            "No Unity Catalog table owns this storage, so readers outside Databricks are invisible "
            "to lineage."
        ]
        evidence = [
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
        storage_evidence, verdict = self._storage_evidence(group, notes)
        if verdict == "read":
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
        known = {t.full_name for t in self.snapshot.tables}
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
                monthly = round(cost.amount / self.window_days * 30, 2)
                currency = cost.currency
                unit = f" {cost.unit}" if cost.unit else ""
                evidence.append(
                    Evidence(
                        source="system.billing.usage",
                        signal=(
                            f"{cost.quantity:,.2f}{unit} in the last {self.window_days} days, "
                            f"{cost.amount:,.2f} {cost.currency} at list price"
                        ),
                    )
                )
                notes.append(
                    "Cost uses Databricks list prices; contract discounts are not applied."
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
