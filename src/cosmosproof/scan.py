"""Runs a scan: reads Unity Catalog and the inventories, then analyzes."""

from __future__ import annotations

from datetime import UTC, date, datetime

from cosmos_semantic.connectors import Connector, connect
from cosmos_semantic.errors import ConnectorError

from cosmosproof import __version__
from cosmosproof.analyzer import Analyzer
from cosmosproof.config import ScanConfig
from cosmosproof.inventory import read_inventory
from cosmosproof.model import Report
from cosmosproof.producers import ProducerActivity, read_producers
from cosmosproof.unity_catalog import CatalogSnapshot, read_catalog

MISSING_GRANTS = (
    "The scanning identity cannot read the Unity Catalog system tables (system.access). "
    "Only a Databricks account admin can grant them; workspace and metastore admins cannot. "
    "Run `cosmosproof grants` and have an account admin run the SQL section."
)


class ScanError(Exception):
    """A scan cannot start; the message says what to do."""


def run_scan(
    config: ScanConfig,
    *,
    connector: Connector | None = None,
    inventories: dict[tuple[str, str], str] | None = None,
) -> Report:
    reference = config.reference_date or date.today()
    if config.databricks is None:
        raise ValueError("the configuration needs a `databricks` section")
    con = connector or connect(config.databricks.source)
    names = config.databricks.system_tables
    producer_notes: list[str] = []
    producers: ProducerActivity | None = None
    try:
        try:
            snapshot: CatalogSnapshot = read_catalog(con, names, reference)
        except ConnectorError as exc:
            if "INSUFFICIENT_PERMISSIONS" in str(exc) or "PERMISSION_DENIED" in str(exc):
                raise ScanError(MISSING_GRANTS) from exc
            raise
        if config.databricks.producers:
            try:
                producers = read_producers(con, names, reference, config.window_days)
                producer_notes = producers.notes
            except Exception as exc:  # optional phase; never block the storage scan
                producer_notes = [f"Jobs and pipelines were not analyzed ({type(exc).__name__})."]
    finally:
        if connector is None:
            con.close()
    excluded = set(config.exclude_catalogs)
    snapshot.tables = [t for t in snapshot.tables if t.full_name.split(".", 1)[0] not in excluded]
    storages = []
    for storage in config.storage:
        path = (inventories or {}).get((storage.account, storage.container)) or storage.inventory
        blobs = read_inventory(path, storage.account, storage.container) if path else []
        storages.append((storage, blobs))
    analyzer = Analyzer(
        snapshot,
        storages,
        reference=reference,
        window_days=config.window_days,
        rates=config.rates,
        orphan_depth=config.orphan_depth,
        producers=producers,
        price_discount=config.databricks.list_price_discount,
    )
    findings = analyzer.run()
    notes = [*analyzer.notes, *producer_notes]
    if not config.storage:
        notes.append("No ADLS inventory was given: sizes, costs and storage reads are unknown.")
    return Report(
        tool_version=__version__,
        generated_at=datetime.now(UTC),
        reference_date=reference,
        window_days=config.window_days,
        findings=findings,
        coverage_notes=notes,
    )
