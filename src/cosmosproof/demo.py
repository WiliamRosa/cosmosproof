"""A small, fictional bank lake for trying CosmosProof without Databricks or Azure."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from cosmosproof import __version__
from cosmosproof.analyzer import Analyzer
from cosmosproof.config import Rates, StorageConfig
from cosmosproof.inventory import Blob, container_url
from cosmosproof.model import Report
from cosmosproof.producers import Producer, ProducerActivity, ProducerCost
from cosmosproof.unity_catalog import Activity, CatalogSnapshot, TableInfo

REFERENCE = date(2026, 11, 26)
ACCOUNT = "bancodemolake"
CONTAINER = "lake"
GB = 1024**3
# Illustrative prices only, so the demo shows a cost column. Real scans take your own rates.
DEMO_RATES = Rates(
    currency="USD",
    per_gb_month={"hot": 0.0208, "cool": 0.0115, "cold": 0.0045, "archive": 0.002},
)


def _at(days_ago: int) -> datetime:
    return datetime.combine(REFERENCE, datetime.min.time(), tzinfo=UTC) - timedelta(days=days_ago)


def _files(
    prefix: str, count: int, total_gb: float, tier: str, accessed: int | None, modified: int
) -> list[Blob]:
    base = container_url(ACCOUNT, CONTAINER)
    size = int(total_gb * GB / count)
    return [
        Blob(
            url=f"{base}{prefix}/part-{i:05d}.parquet",
            size=size,
            tier=tier,
            last_modified=_at(modified),
            last_access=_at(accessed) if accessed is not None else None,
        )
        for i in range(count)
    ]


def demo_inputs() -> tuple[CatalogSnapshot, list[tuple[StorageConfig, list[Blob]]]]:
    loc = container_url(ACCOUNT, CONTAINER)
    tables = [
        TableInfo(
            "main.raw.clientes_legado",
            "EXTERNAL",
            "data-eng-legado",
            f"{loc}raw/clientes_legado",
            "DELTA",
            _at(900),
            ["id_cliente", "cpf", "nome_completo", "email", "data_cadastro"],
        ),
        TableInfo(
            "main.bronze.transacoes_cdc",
            "EXTERNAL",
            "plataforma-ingestao",
            f"{loc}bronze/transacoes_cdc",
            "DELTA",
            _at(500),
            ["id_transacao", "id_conta", "valor", "data_transacao"],
        ),
        TableInfo(
            "main.silver.contas",
            "EXTERNAL",
            "dados-core",
            f"{loc}silver/contas",
            "DELTA",
            _at(700),
            ["id_conta", "id_cliente", "saldo", "agencia"],
        ),
        TableInfo(
            "main.gold.kpi_diario",
            "MANAGED",
            "analytics",
            None,
            "DELTA",
            _at(400),
            ["data", "receita", "clientes_ativos"],
        ),
        TableInfo(
            "main.sandbox.experimento_novo",
            "EXTERNAL",
            "ciencia-dados",
            f"{loc}sandbox/experimento_novo",
            "DELTA",
            _at(20),
            ["feature_a", "feature_b"],
        ),
    ]
    activity = Activity(
        table_reads={
            "main.raw.clientes_legado": _at(310),
            "main.silver.contas": _at(1),
            "main.gold.kpi_diario": _at(0),
        },
        table_read_counts={
            "main.raw.clientes_legado": 4,
            "main.silver.contas": 9120,
            "main.gold.kpi_diario": 3311,
        },
        table_writes={"main.bronze.transacoes_cdc": _at(0), "main.gold.kpi_diario": _at(0)},
        path_reads={},
        earliest_event=_at(390),
    )
    blobs = (
        _files("raw/clientes_legado", 40, 180.0, "Hot", accessed=305, modified=600)
        + _files("bronze/transacoes_cdc", 120, 640.0, "Hot", accessed=200, modified=0)
        + _files("silver/contas", 30, 90.0, "Hot", accessed=1, modified=1)
        + _files("sandbox/experimento_novo", 5, 2.0, "Hot", accessed=3, modified=3)
        + _files("exports/campanha_2024", 60, 300.0, "Cool", accessed=420, modified=700)
    )
    storage = StorageConfig(
        account=ACCOUNT, container=CONTAINER, access_tracking_since=REFERENCE - timedelta(days=400)
    )
    return CatalogSnapshot(tables=tables, activity=activity), [(storage, blobs)]


def demo_producers() -> ProducerActivity:
    """A Lakeflow Connect pipeline ingesting from SQL Server into a table nobody reads, and a
    job that builds the accounts table dashboards use."""
    ingest, build = "pipeline:7f3e-ingest", "job:4412"
    return ProducerActivity(
        writes={
            ingest: {"main.bronze.transacoes_cdc": _at(0)},
            build: {"main.silver.contas": _at(1)},
        },
        reads_by={
            "main.raw.clientes_legado": {"other": _at(310)},
            "main.silver.contas": {"other": _at(1)},
            "main.gold.kpi_diario": {"other": _at(0)},
        },
        producers={
            ingest: Producer(
                ingest, "ingestao-transacoes-sqlserver", "plataforma-ingestao", "INGESTION_PIPELINE"
            ),
            build: Producer(build, "build-contas", "dados-core"),
        },
        costs={ingest: ProducerCost(2160.0, "USD", 4320.0, "DBU")},
    )


def demo_report(window_days: int = 180) -> Report:
    snapshot, storages = demo_inputs()
    analyzer = Analyzer(
        snapshot,
        storages,
        reference=REFERENCE,
        window_days=window_days,
        rates=DEMO_RATES,
        producers=demo_producers(),
    )
    findings = analyzer.run()
    return Report(
        tool_version=__version__,
        generated_at=datetime.now(UTC),
        reference_date=REFERENCE,
        window_days=window_days,
        findings=findings,
        storage_files=sum(len(blobs) for _, blobs in storages),
        coverage_notes=[
            *analyzer.notes,
            "Demo data: a fictional bank lake with illustrative prices.",
        ],
    )
