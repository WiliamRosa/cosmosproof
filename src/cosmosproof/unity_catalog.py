"""Reads tables, columns and read/write activity from the Unity Catalog system tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from cosmos_semantic.connectors import Connector
from cosmos_semantic.errors import ConnectorError

from cosmosproof.config import SystemTables

# Lineage system tables keep about one year of events (Azure documents a rolling year,
# AWS 395 days); looking further back only costs scan time.
LINEAGE_HISTORY_DAYS = 395


@dataclass
class TableInfo:
    full_name: str
    table_type: str
    owner: str | None
    storage_path: str | None
    data_source_format: str | None
    created: datetime | None
    columns: list[str] = field(default_factory=list)
    # Excluded from findings, but still the owner of its storage (so it is never an orphan).
    ignored: bool = False


@dataclass
class Activity:
    """Last read and write per table name and per storage path, from table lineage."""

    table_reads: dict[str, datetime] = field(default_factory=dict)
    table_read_counts: dict[str, int] = field(default_factory=dict)
    table_writes: dict[str, datetime] = field(default_factory=dict)
    path_reads: dict[str, datetime] = field(default_factory=dict)
    earliest_event: datetime | None = None
    # False when the identity cannot read system.access (no account admin grant): the scan
    # then relies on storage signals only.
    lineage_available: bool = True


@dataclass
class CatalogSnapshot:
    tables: list[TableInfo]
    activity: Activity


def is_permission_error(exc: Exception) -> bool:
    text = str(exc)
    return "INSUFFICIENT_PERMISSIONS" in text or "PERMISSION_DENIED" in text


def _lit(value: date) -> str:
    return f"DATE '{value.isoformat()}'"


def read_catalog(con: Connector, names: SystemTables, reference: date) -> CatalogSnapshot:
    since = _lit(reference - timedelta(days=LINEAGE_HISTORY_DAYS))
    tables_sql = f"""
        SELECT table_catalog, table_schema, table_name, table_type, table_owner,
               storage_path, data_source_format, created
        FROM {names.tables}
        WHERE table_catalog <> 'system' AND table_schema <> 'information_schema'
    """
    columns_sql = f"""
        SELECT table_catalog, table_schema, table_name, column_name
        FROM {names.columns}
        WHERE table_catalog <> 'system' AND table_schema <> 'information_schema'
    """
    reads_sql = f"""
        SELECT source_table_full_name AS name, MAX(event_time) AS last_event, COUNT(*) AS events
        FROM {names.lineage}
        WHERE source_table_full_name IS NOT NULL AND event_date >= {since}
        GROUP BY source_table_full_name
    """
    writes_sql = f"""
        SELECT target_table_full_name AS name, MAX(event_time) AS last_event
        FROM {names.lineage}
        WHERE target_table_full_name IS NOT NULL AND event_date >= {since}
        GROUP BY target_table_full_name
    """
    paths_sql = f"""
        SELECT source_path AS path, MAX(event_time) AS last_event
        FROM {names.lineage}
        WHERE source_path IS NOT NULL AND event_date >= {since}
        GROUP BY source_path
    """
    earliest_sql = (
        f"SELECT MIN(event_time) AS earliest FROM {names.lineage} WHERE event_date >= {since}"
    )

    tables: dict[str, TableInfo] = {}
    for row in con.execute(tables_sql).to_pylist():
        name = f"{row['table_catalog']}.{row['table_schema']}.{row['table_name']}"
        tables[name] = TableInfo(
            full_name=name,
            table_type=str(row["table_type"] or ""),
            owner=row["table_owner"],
            # Managed tables can report an empty string instead of NULL.
            storage_path=row["storage_path"] or None,
            data_source_format=row["data_source_format"],
            created=row["created"],
        )
    for row in con.execute(columns_sql).to_pylist():
        name = f"{row['table_catalog']}.{row['table_schema']}.{row['table_name']}"
        if name in tables:
            tables[name].columns.append(row["column_name"])

    activity = Activity()
    try:
        reads = con.execute(reads_sql).to_pylist()
    except ConnectorError as exc:
        if not is_permission_error(exc):
            raise
        activity.lineage_available = False
        return CatalogSnapshot(tables=list(tables.values()), activity=activity)
    for row in reads:
        activity.table_reads[row["name"]] = row["last_event"]
        activity.table_read_counts[row["name"]] = int(row["events"])
    for row in con.execute(writes_sql).to_pylist():
        activity.table_writes[row["name"]] = row["last_event"]
    for row in con.execute(paths_sql).to_pylist():
        activity.path_reads[row["path"]] = row["last_event"]
    earliest = con.execute(earliest_sql).to_pylist()
    activity.earliest_event = earliest[0]["earliest"] if earliest else None
    return CatalogSnapshot(tables=list(tables.values()), activity=activity)
