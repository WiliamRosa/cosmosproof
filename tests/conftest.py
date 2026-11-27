from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from cosmos_semantic.connectors import DataSourceConfig, connect

from cosmosproof.config import SystemTables

REFERENCE = date(2026, 11, 26)
LOC = "abfss://lake@acct.dfs.core.windows.net"


def at(days_ago: int) -> datetime:
    return datetime.combine(REFERENCE, datetime.min.time(), tzinfo=UTC) - timedelta(days=days_ago)


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
    event_time TIMESTAMP, event_date DATE
);
INSERT INTO uc_lineage VALUES
    ('main.silver.contas', NULL, NULL, TIMESTAMP '2026-11-20 10:00:00', DATE '2026-11-20'),
    ('main.silver.contas', NULL, NULL, TIMESTAMP '2026-11-25 10:00:00', DATE '2026-11-25'),
    ('main.raw.clientes', NULL, NULL, TIMESTAMP '2026-01-10 10:00:00', DATE '2026-01-10'),
    (NULL, 'main.raw.clientes', NULL, TIMESTAMP '2026-11-25 03:00:00', DATE '2026-11-25'),
    (NULL, NULL, '{LOC}/exports/x', TIMESTAMP '2026-11-01 10:00:00', DATE '2026-11-01'),
    ('main.silver.contas', NULL, NULL, TIMESTAMP '2024-01-01 10:00:00', DATE '2024-01-01');
"""

NAMES = SystemTables(lineage="uc_lineage", tables="uc_tables", columns="uc_columns")


@pytest.fixture
def duck():
    con = connect(DataSourceConfig(type="duckdb", max_rows=100_000))
    con.run_script(SETUP)
    yield con
    con.close()
