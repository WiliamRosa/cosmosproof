from conftest import REFERENCE, at

from cosmosproof.analyzer import Analyzer
from cosmosproof.federation import build_snapshot
from cosmosproof.unity_catalog import Activity, CatalogSnapshot

OLD = int(at(400).timestamp() * 1000)
CONNECTIONS = [
    {
        "name": "pg_crm",
        "connection_type": "POSTGRESQL",
        "owner": "dba",
        "credential_type": "USERNAME_PASSWORD",
        "options": {"host": "crm.postgres.database.azure.com", "port": "5432"},
        "created_at": OLD,
    },
    {"name": "sql_erp", "connection_type": "SQLSERVER", "owner": "dba", "created_at": OLD},
    {"name": "sql_ingest", "connection_type": "SQLSERVER", "owner": "eng", "created_at": OLD},
    {"name": "pg_orphan", "connection_type": "POSTGRESQL", "owner": "x", "created_at": OLD},
]
CATALOGS = [
    {"name": "crm", "catalog_type": "FOREIGN_CATALOG", "connection_name": "pg_crm"},
    {"name": "erp", "catalog_type": "FOREIGN_CATALOG", "connection_name": "sql_erp"},
    {"name": "main", "catalog_type": "MANAGED_CATALOG"},
]
PIPELINES = [{"name": "ingest-orders", "connection_name": "sql_ingest"}]


def _run(reads, pipelines=PIPELINES, lineage=True):
    fed = build_snapshot(CONNECTIONS, CATALOGS, pipelines)
    snap = CatalogSnapshot(
        [], Activity(table_reads=reads, earliest_event=at(390), lineage_available=lineage)
    )
    analyzer = Analyzer(snap, [], reference=REFERENCE, window_days=180, federation=fed)
    return analyzer.run(), analyzer


def test_snapshot_links_catalogs_and_pipelines():
    fed = build_snapshot(CONNECTIONS, CATALOGS, PIPELINES)
    by = {c.name: c for c in fed.connections}
    assert by["pg_crm"].catalogs == ["crm"] and by["pg_crm"].host.startswith("crm.")
    assert by["sql_ingest"].pipelines == ["ingest-orders"]
    assert by["pg_orphan"].catalogs == [] and fed.pipelines_checked


def test_unused_connections_are_risk_findings():
    findings, _ = _run({"erp.dbo.orders": at(3), "crm.public.leads": at(300)})
    assets = {f.asset: f for f in findings}
    # pg_crm: last read 300 days ago; pg_orphan: no catalog and no pipeline.
    assert set(assets) == {"connection pg_crm", "connection pg_orphan"}
    crm = assets["connection pg_crm"]
    assert (crm.reading, crm.kind, crm.confidence) == ("risk", "unused_connection", "medium")
    assert "USERNAME_PASSWORD" in crm.evidence[0].signal


def test_catalogless_connections_need_the_pipeline_list():
    findings, _ = _run({"erp.dbo.orders": at(3)}, pipelines=None)
    assert {f.asset for f in findings} == {"connection pg_crm"}


def test_storage_only_mode_does_not_judge_connections():
    findings, analyzer = _run({}, lineage=False)
    assert not any(f.kind == "unused_connection" for f in findings)
    assert any("Federation connections were not judged" in n for n in analyzer.notes)
