"""Producers (Lakeflow jobs and pipelines, which include Lakeflow Connect ingestion): which
tables each one writes, who reads them, and what each producer costs at list price."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import sqlglot
from cosmos_semantic.connectors import Connector

from cosmosproof.config import SystemTables
from cosmosproof.unity_catalog import LINEAGE_HISTORY_DAYS

# Lineage attributes an event to a job or a pipeline through entity_metadata.
_ENTITY = """CASE
    WHEN entity_metadata.job_info IS NOT NULL
        THEN CONCAT('job:', entity_metadata.job_info.job_id)
    WHEN entity_metadata.dlt_pipeline_info IS NOT NULL
        THEN CONCAT('pipeline:', entity_metadata.dlt_pipeline_info.dlt_pipeline_id)
    ELSE 'other'
END"""


@dataclass
class Producer:
    key: str  # "job:<id>" or "pipeline:<id>"
    name: str | None = None
    owner: str | None = None
    kind_detail: str | None = None  # pipeline type, e.g. INGESTION_PIPELINE
    deleted: bool = False


@dataclass
class ProducerCost:
    amount: float
    currency: str | None
    quantity: float
    unit: str | None


@dataclass
class ProducerActivity:
    writes: dict[str, dict[str, datetime]] = field(
        default_factory=dict
    )  # producer -> table -> last
    reads_by: dict[str, dict[str, datetime]] = field(
        default_factory=dict
    )  # table -> entity -> last
    producers: dict[str, Producer] = field(default_factory=dict)
    costs: dict[str, ProducerCost] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _run(con: Connector, sql: str) -> list[dict]:
    """Queries are written in Databricks SQL and transpiled for the connector (DuckDB in tests)."""
    statement = sqlglot.transpile(sql, read="databricks", write=con.dialect)[0]
    return con.execute(statement).to_pylist()


def _lit(value: date) -> str:
    return f"DATE '{value.isoformat()}'"


def read_producers(
    con: Connector, names: SystemTables, reference: date, window_days: int
) -> ProducerActivity:
    since = _lit(reference - timedelta(days=LINEAGE_HISTORY_DAYS))
    window_start = _lit(reference - timedelta(days=window_days))
    out = ProducerActivity()

    for row in _run(
        con,
        f"""
        SELECT {_ENTITY} AS producer, target_table_full_name AS name, MAX(event_time) AS last_event
        FROM {names.lineage}
        WHERE target_table_full_name IS NOT NULL AND event_date >= {since}
          AND (entity_metadata.job_info IS NOT NULL OR entity_metadata.dlt_pipeline_info IS NOT NULL)
        GROUP BY 1, 2
        """,
    ):
        out.writes.setdefault(row["producer"], {})[row["name"]] = row["last_event"]

    for row in _run(
        con,
        f"""
        SELECT source_table_full_name AS name, {_ENTITY} AS entity, MAX(event_time) AS last_event
        FROM {names.lineage}
        WHERE source_table_full_name IS NOT NULL AND event_date >= {since}
        GROUP BY 1, 2
        """,
    ):
        out.reads_by.setdefault(row["name"], {})[row["entity"]] = row["last_event"]

    _read_names(con, names, out)
    _read_costs(con, names, window_start, out)
    return out


def _latest(rows: list[dict], key: str) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        current = latest.get(row[key])
        if current is None or (row["change_time"] or datetime.min) > (
            current["change_time"] or datetime.min
        ):
            latest[row[key]] = row
    return latest


def _read_names(con: Connector, names: SystemTables, out: ProducerActivity) -> None:
    try:
        jobs = _latest(
            _run(
                con,
                f"SELECT job_id, name, run_as_user_name, creator_user_name, change_time, delete_time "
                f"FROM {names.jobs}",
            ),
            "job_id",
        )
        pipelines = _latest(
            _run(
                con,
                f"SELECT pipeline_id, name, pipeline_type, run_as, created_by, change_time, delete_time "
                f"FROM {names.pipelines}",
            ),
            "pipeline_id",
        )
    except Exception as exc:  # grants on system.lakeflow are often missing
        out.notes.append(f"Job and pipeline names are unavailable ({type(exc).__name__}).")
        return
    for job_id, row in jobs.items():
        key = f"job:{job_id}"
        out.producers[key] = Producer(
            key,
            row["name"],
            row["run_as_user_name"] or row["creator_user_name"],
            None,
            row["delete_time"] is not None,
        )
    for pipeline_id, row in pipelines.items():
        key = f"pipeline:{pipeline_id}"
        out.producers[key] = Producer(
            key,
            row["name"],
            row["run_as"] or row["created_by"],
            row["pipeline_type"],
            row["delete_time"] is not None,
        )


def _read_costs(
    con: Connector, names: SystemTables, window_start: str, out: ProducerActivity
) -> None:
    try:
        rows = _run(
            con,
            f"""
            SELECT
                CASE WHEN u.usage_metadata.job_id IS NOT NULL
                     THEN CONCAT('job:', u.usage_metadata.job_id)
                     ELSE CONCAT('pipeline:', u.usage_metadata.dlt_pipeline_id) END AS producer,
                u.usage_unit AS unit,
                SUM(u.usage_quantity) AS quantity,
                SUM(u.usage_quantity * p.pricing.effective_list.`default`) AS amount,
                MAX(p.currency_code) AS currency,
                COUNT(p.sku_name) AS priced,
                COUNT(*) AS records
            FROM {names.billing_usage} u
            LEFT JOIN {names.list_prices} p
              ON u.sku_name = p.sku_name AND u.cloud = p.cloud AND u.usage_unit = p.usage_unit
             AND u.usage_end_time > p.price_start_time
             AND (p.price_end_time IS NULL OR u.usage_end_time <= p.price_end_time)
            WHERE u.usage_date >= {window_start}
              AND (u.usage_metadata.job_id IS NOT NULL OR u.usage_metadata.dlt_pipeline_id IS NOT NULL)
            GROUP BY 1, 2
            """,
        )
    except Exception as exc:  # system.billing needs its own grant
        out.notes.append(f"Job and pipeline costs are unavailable ({type(exc).__name__}).")
        return
    merged: dict[str, ProducerCost] = {}
    unpriced: set[str] = set()
    for row in rows:
        if int(row["priced"]) < int(row["records"]):
            unpriced.add(row["producer"])
        cost = merged.get(row["producer"])
        amount = float(row["amount"] or 0)
        quantity = float(row["quantity"] or 0)
        if cost is None:
            merged[row["producer"]] = ProducerCost(amount, row["currency"], quantity, row["unit"])
        else:
            cost.amount += amount
            cost.quantity += quantity
            if cost.unit != row["unit"]:
                cost.unit = None
    out.costs = merged
    for key in sorted(unpriced):
        out.notes.append(f"Some usage of {key} has no list price; its cost is understated.")


def outside_reads(activity: ProducerActivity, producer: str, table: str) -> list[datetime]:
    """Reads of a table by anyone other than the producer itself."""
    return [t for entity, t in activity.reads_by.get(table, {}).items() if entity != producer]


def tables_by_producer(activity: ProducerActivity) -> dict[str, list[str]]:
    fed_by: dict[str, list[str]] = defaultdict(list)
    for producer, tables in activity.writes.items():
        for table in tables:
            fed_by[table].append(producer)
    return {table: sorted(producers) for table, producers in fed_by.items()}
