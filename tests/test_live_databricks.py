"""Opt-in: runs the Unity Catalog queries against a real SQL warehouse (`pytest -m databricks`)."""

import os
from datetime import date

import pytest

from cosmosproof.config import SystemTables
from cosmosproof.unity_catalog import read_catalog

pytestmark = pytest.mark.databricks


def test_system_table_queries_run():
    profile = os.environ.get("COSMOSPROOF_DATABRICKS_PROFILE")
    http_path = os.environ.get("COSMOSPROOF_DATABRICKS_HTTP_PATH")
    if not profile or not http_path:
        pytest.skip("set COSMOSPROOF_DATABRICKS_PROFILE and COSMOSPROOF_DATABRICKS_HTTP_PATH")
    from cosmos_semantic.connectors import DataSourceConfig, connect

    con = connect(
        DataSourceConfig(
            type="databricks",
            options={"profile": profile, "http_path": http_path},
            max_rows=1_000_000,
            timeout_seconds=300,
        )
    )
    try:
        snap = read_catalog(con, SystemTables(), date.today())
    finally:
        con.close()
    assert snap.tables
    assert all(t.storage_path != "" for t in snap.tables)
