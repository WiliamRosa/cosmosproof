from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from cosmos_semantic.connectors import DataSourceConfig, connect

from cosmosproof.config import SystemTables

REFERENCE = date(2026, 11, 26)
LOC = "abfss://lake@acct.dfs.core.windows.net"


def at(days_ago: int) -> datetime:
    return datetime.combine(REFERENCE, datetime.min.time(), tzinfo=UTC) - timedelta(days=days_ago)


def _entity(job: str | None = None, pipeline: str | None = None) -> str:
    job_info = f"{{'job_id': '{job}', 'job_run_id': 'r'}}" if job else "NULL"
    pipe_info = f"{{'dlt_pipeline_id': '{pipeline}', 'dlt_update_id': 'u'}}" if pipeline else "NULL"
    return f"{{'job_info': {job_info}, 'dlt_pipeline_info': {pipe_info}}}"


JOB7, JOB8, PIPE1 = _entity(job="7"), _entity(job="8"), _entity(pipeline="p1")

SETUP = f"""
CREATE TABLE uc_tables (
    table_catalog VARCHAR, table_schema VARCHAR, table_name VARCHAR, table_type VARCHAR,
    table_owner VARCHAR, storage_path VARCHAR, data_source_format VARCHAR, created TIMESTAMP
);
INSERT INTO uc_tables VALUES
    ('main', 'raw', 'clientes', 'EXTERNAL', 'legado', '{LOC}/raw/clientes', 'DELTA', TIMESTAMP '2024-01-01'),
    ('main', 'silver', 'contas', 'EXTERNAL', 'core', '{LOC}/silver/contas', 'DELTA', TIMESTAMP '2024-01-01'),
    ('main', 'gold', 'kpi_view', 'VIEW', 'bi', NULL, NULL, TIMESTAMP '2024-01-01'),
    ('main', 'information_schema', 'tables', 'VIEW', NULL, NULL, NULL, NULL),
    ('samples', 'tpch', 'orders', 'MANAGED', 'System user', '', 'DELTA', TIMESTAMP '2024-01-01'),
    ('system', 'access', 'table_lineage', 'MANAGED', NULL, NULL, NULL, NULL);
CREATE TABLE uc_columns (
    table_catalog VARCHAR, table_schema VARCHAR, table_name VARCHAR, column_name VARCHAR
);
INSERT INTO uc_columns VALUES
    ('main', 'raw', 'clientes', 'cpf'),
    ('main', 'raw', 'clientes', 'valor'),
    ('main', 'silver', 'contas', 'saldo');
CREATE TABLE uc_lineage (
    source_table_full_name VARCHAR, target_table_full_name VARCHAR, source_path VARCHAR,
    event_time TIMESTAMP, event_date DATE,
    entity_metadata STRUCT(
        job_info STRUCT(job_id VARCHAR, job_run_id VARCHAR),
        dlt_pipeline_info STRUCT(dlt_pipeline_id VARCHAR, dlt_update_id VARCHAR)
    )
);
INSERT INTO uc_lineage VALUES
    ('main.silver.contas', NULL, NULL, TIMESTAMP '2026-11-20 10:00:00', DATE '2026-11-20', NULL),
    ('main.silver.contas', NULL, NULL, TIMESTAMP '2026-11-25 10:00:00', DATE '2026-11-25', NULL),
    ('main.raw.clientes', NULL, NULL, TIMESTAMP '2026-01-10 10:00:00', DATE '2026-01-10', NULL),
    (NULL, 'main.raw.clientes', NULL, TIMESTAMP '2026-11-25 03:00:00', DATE '2026-11-25', {JOB7}),
    (NULL, NULL, '{LOC}/exports/x', TIMESTAMP '2026-11-01 10:00:00', DATE '2026-11-01', NULL),
    ('main.silver.contas', NULL, NULL, TIMESTAMP '2024-01-01 10:00:00', DATE '2024-01-01', NULL),
    (NULL, 'main.silver.contas', NULL, TIMESTAMP '2026-11-25 04:00:00', DATE '2026-11-25', {PIPE1}),
    (NULL, 'main.raw.clientes', NULL, TIMESTAMP '2026-11-24 03:00:00', DATE '2026-11-24', {JOB8}),
    -- job 7 reads its own output (a MERGE): that is not use.
    ('main.raw.clientes', NULL, NULL, TIMESTAMP '2026-11-25 02:59:00', DATE '2026-11-25', {JOB7});
CREATE TABLE uc_jobs (
    job_id VARCHAR, name VARCHAR, run_as_user_name VARCHAR, creator_user_name VARCHAR,
    change_time TIMESTAMP, delete_time TIMESTAMP
);
INSERT INTO uc_jobs VALUES
    ('7', 'old name', 'etl@bank', 'someone', TIMESTAMP '2025-01-01', NULL),
    ('7', 'carga clientes', 'etl@bank', 'someone', TIMESTAMP '2026-02-01', NULL),
    ('8', 'retired job', 'etl@bank', 'someone', TIMESTAMP '2026-11-25', TIMESTAMP '2026-11-25');
CREATE TABLE uc_pipelines (
    pipeline_id VARCHAR, name VARCHAR, pipeline_type VARCHAR, run_as VARCHAR, created_by VARCHAR,
    change_time TIMESTAMP, delete_time TIMESTAMP
);
INSERT INTO uc_pipelines VALUES
    ('p1', 'ingest contas', 'INGESTION_PIPELINE', 'ingest@bank', 'x', TIMESTAMP '2026-01-01', NULL);
CREATE TABLE uc_usage (
    sku_name VARCHAR, cloud VARCHAR, usage_unit VARCHAR, usage_quantity DECIMAL(20, 6),
    usage_end_time TIMESTAMP, usage_date DATE,
    usage_metadata STRUCT(job_id VARCHAR, dlt_pipeline_id VARCHAR)
);
INSERT INTO uc_usage VALUES
    ('JOBS', 'AZURE', 'DBU', 6, TIMESTAMP '2026-11-10', DATE '2026-11-09', {{'job_id': '7', 'dlt_pipeline_id': NULL}}),
    ('JOBS', 'AZURE', 'DBU', 4, TIMESTAMP '2026-11-20', DATE '2026-11-19', {{'job_id': '7', 'dlt_pipeline_id': NULL}}),
    ('JOBS', 'AZURE', 'DBU', 99, TIMESTAMP '2025-01-02', DATE '2025-01-01', {{'job_id': '7', 'dlt_pipeline_id': NULL}}),
    ('DLT_NEW', 'AZURE', 'DBU', 3, TIMESTAMP '2026-11-20', DATE '2026-11-19', {{'job_id': NULL, 'dlt_pipeline_id': 'p1'}});
CREATE TABLE uc_prices (
    sku_name VARCHAR, cloud VARCHAR, usage_unit VARCHAR, currency_code VARCHAR,
    price_start_time TIMESTAMP, price_end_time TIMESTAMP,
    pricing STRUCT(effective_list STRUCT("default" DECIMAL(20, 6)))
);
INSERT INTO uc_prices VALUES
    ('JOBS', 'AZURE', 'DBU', 'USD', TIMESTAMP '2020-01-01', TIMESTAMP '2026-11-15', {{'effective_list': {{'default': 0.5}}}}),
    ('JOBS', 'AZURE', 'DBU', 'USD', TIMESTAMP '2026-11-15', NULL, {{'effective_list': {{'default': 1.0}}}});
"""

NAMES = SystemTables(
    lineage="uc_lineage",
    tables="uc_tables",
    columns="uc_columns",
    jobs="uc_jobs",
    pipelines="uc_pipelines",
    billing_usage="uc_usage",
    list_prices="uc_prices",
)


@pytest.fixture
def duck():
    con = connect(DataSourceConfig(type="duckdb", max_rows=100_000))
    con.run_script(SETUP)
    yield con
    con.close()
