from datetime import UTC, datetime, timedelta

from conftest import LOC, REFERENCE, at

from cosmosproof.analyzer import Analyzer
from cosmosproof.config import AccessLogs, StorageConfig
from cosmosproof.inventory import Blob
from cosmosproof.storage_logs import parse_rows, query_text
from cosmosproof.unity_catalog import Activity, CatalogSnapshot, TableInfo

NOW = datetime(2026, 11, 27, 14, 0, tzinfo=UTC)


def test_query_filters_reads_of_one_container():
    text = query_text("acct", "lake", datetime(2026, 11, 27, 12, 37, tzinfo=UTC))
    assert "OperationName in ('GetBlob', 'ReadFile')" in text
    assert "AccountName == 'acct'" in text and "startswith '/lake/'" in text
    assert "datetime(2026-11-27T12:37:00+00:00)" in text


def test_rows_become_abfss_urls():
    rows = [
        ["/lake/lab/silver/t/part%2D0.parquet", "2026-11-27T13:00:00Z", 3],
        ["/lake/lab/silver/t/part-0.parquet", "2026-11-27T13:30:00Z", 1],
    ]
    out = parse_rows(rows, "acct", "lake")
    assert out == {f"{LOC}/lab/silver/t/part-0.parquet": datetime(2026, 11, 27, 13, 30, tzinfo=UTC)}


def _run(log_read, logs_since, window_hours=0.5, created_days_ago=1):
    storage = StorageConfig(
        account="acct",
        container="lake",
        access_logs=AccessLogs(workspace_id="ws", since=logs_since),
    )
    blob = Blob(f"{LOC}/t/part-0.parquet", 1024, "Hot", at(1), None, log_read=log_read)
    log = Blob(f"{LOC}/t/_delta_log/0.json", 10, "Hot", at(1), None, log_read=NOW)
    table = TableInfo("m.s.t", "EXTERNAL", "owner", f"{LOC}/t", "DELTA", at(created_days_ago))
    snap = CatalogSnapshot([table], Activity(lineage_available=False))
    analyzer = Analyzer(
        snap,
        [(storage, [blob, log])],
        reference=REFERENCE,
        window_days=180,
        window_hours=window_hours,
        now=NOW,
    )
    return analyzer.run(), analyzer


def test_hour_window_with_logs_finds_unread_tables():
    findings, analyzer = _run(log_read=None, logs_since=NOW - timedelta(hours=2))
    (f,) = findings
    assert f.confidence == "medium"
    assert any(e.source == "Azure Storage resource logs" for e in f.evidence)
    assert f.window_days == round(0.5 / 24, 4)
    assert analyzer.cutoff == NOW - timedelta(minutes=30)


def test_logged_read_inside_the_window_means_used():
    findings, _ = _run(log_read=NOW - timedelta(minutes=5), logs_since=NOW - timedelta(hours=2))
    assert findings == []


def test_logs_enabled_after_the_window_start_cannot_judge():
    findings, _ = _run(log_read=None, logs_since=NOW - timedelta(minutes=10))
    assert findings == []
