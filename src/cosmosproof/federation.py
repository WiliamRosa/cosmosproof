"""Lakehouse Federation connections and the foreign catalogs built on them (risk reading).

A connection holds credentials to a production database (PostgreSQL, SQL Server and others).
One that nothing uses is attack surface with no business value. Connections and the catalog
that uses each one come from the Unity Catalog REST API: system.information_schema does not
link catalogs to connections. Use comes from lineage on the foreign catalogs' tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Connection:
    name: str
    connection_type: str | None
    owner: str | None
    credential_type: str | None
    host: str | None
    created: datetime | None
    catalogs: list[str] = field(default_factory=list)
    # Ingestion pipelines (Lakeflow Connect) that use the connection, when known.
    pipelines: list[str] = field(default_factory=list)


@dataclass
class FederationSnapshot:
    connections: list[Connection]
    pipelines_checked: bool
    notes: list[str] = field(default_factory=list)


def _millis(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC)


def build_snapshot(
    connections: list[dict], catalogs: list[dict], pipelines: list[dict] | None
) -> FederationSnapshot:
    by_name: dict[str, Connection] = {}
    for c in connections:
        options = c.get("options") or {}
        by_name[c["name"]] = Connection(
            name=c["name"],
            connection_type=c.get("connection_type"),
            owner=c.get("owner"),
            credential_type=c.get("credential_type"),
            host=options.get("host"),
            created=_millis(c.get("created_at")),
        )
    for cat in catalogs:
        if cat.get("catalog_type") == "FOREIGN_CATALOG" and cat.get("connection_name") in by_name:
            by_name[cat["connection_name"]].catalogs.append(cat["name"])
    for p in pipelines or []:
        name = p.get("connection_name")
        if name in by_name:
            by_name[name].pipelines.append(p.get("name") or p.get("pipeline_id") or "?")
    return FederationSnapshot(
        connections=sorted(by_name.values(), key=lambda c: c.name),
        pipelines_checked=pipelines is not None,
    )


def read_federation(host: str, token: str) -> FederationSnapshot:
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient(host=f"https://{host}", token=token)
    connections = [c.as_dict() for c in w.connections.list()]
    catalogs = [c.as_dict() for c in w.catalogs.list()]
    pipelines: list[dict] | None = []
    notes: list[str] = []
    try:
        for p in w.pipelines.list_pipelines():
            spec = w.pipelines.get(p.pipeline_id).spec
            ingestion = getattr(spec, "ingestion_definition", None) if spec else None
            if ingestion and ingestion.connection_name:
                pipelines.append(
                    {
                        "name": p.name,
                        "pipeline_id": p.pipeline_id,
                        "connection_name": ingestion.connection_name,
                    }
                )
    except Exception as exc:  # listing pipelines needs its own permission
        pipelines = None
        notes.append(f"Ingestion pipelines could not be listed ({type(exc).__name__}).")
    snapshot = build_snapshot(connections, catalogs, pipelines)
    snapshot.notes.extend(notes)
    return snapshot
