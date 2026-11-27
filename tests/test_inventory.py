from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq

from cosmosproof.inventory import parse_time, read_inventory

CSV = """Name,Creation-Time,Last-Modified,Content-Length,AccessTier,LastAccessTime,hdi_isfolder
raw/clientes,2024-01-01T00:00:00.0000000Z,2024-01-01T00:00:00.0000000Z,0,,,true
raw/clientes/part-0.parquet,2024-01-01T00:00:00.0000000Z,2025-03-04T05:06:07.1234567Z,1024,Hot,2026-01-02T03:04:05.0000000Z,
raw/clientes/part-1.parquet,2024-01-01T00:00:00.0000000Z,"Tue, 04 Mar 2025 05:06:07 GMT",2048,Cool,,
"""


def test_csv_inventory(tmp_path):
    path = tmp_path / "inv.csv"
    path.write_text(CSV, encoding="utf-8")
    blobs = read_inventory(path, "acct", "lake")
    assert [b.url for b in blobs] == [
        "abfss://lake@acct.dfs.core.windows.net/raw/clientes/part-0.parquet",
        "abfss://lake@acct.dfs.core.windows.net/raw/clientes/part-1.parquet",
    ]
    assert blobs[0].size == 1024 and blobs[0].tier == "Hot"
    assert blobs[0].last_modified == datetime(2025, 3, 4, 5, 6, 7, 123456, tzinfo=UTC)
    assert blobs[0].last_access == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert blobs[1].last_modified == datetime(2025, 3, 4, 5, 6, 7, tzinfo=UTC)
    assert blobs[1].last_access is None


def test_parquet_inventory(tmp_path):
    path = tmp_path / "inv.parquet"
    pq.write_table(
        pa.table({"Name": ["a/b.parquet"], "Content-Length": [10], "AccessTier": ["Cold"]}), path
    )
    (blob,) = read_inventory(path, "acct", "lake")
    assert blob.size == 10 and blob.tier == "Cold" and blob.last_access is None


def test_parse_time_rejects_garbage():
    assert parse_time("not a date") is None
    assert parse_time("") is None
