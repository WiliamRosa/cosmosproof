from datetime import timedelta

from conftest import LOC, REFERENCE, at

from cosmosproof.analyzer import Analyzer
from cosmosproof.config import Rates, StorageConfig
from cosmosproof.inventory import Blob
from cosmosproof.unity_catalog import Activity, CatalogSnapshot, TableInfo

GB = 1024**3
TRACKED = StorageConfig(
    account="acct", container="lake", access_tracking_since=REFERENCE - timedelta(days=400)
)
UNTRACKED = StorageConfig(account="acct", container="lake")


def table(name, path, columns=(), created=900, ttype="EXTERNAL"):
    return TableInfo(
        name, ttype, "owner", f"{LOC}/{path}" if path else None, "DELTA", at(created), list(columns)
    )


def blob(path, gb=1.0, tier="Hot", accessed=None, modified=500):
    return Blob(
        f"{LOC}/{path}",
        int(gb * GB),
        tier,
        at(modified),
        at(accessed) if accessed is not None else None,
    )


def run(
    tables, blobs=(), storage=TRACKED, reads=None, writes=None, paths=None, rates=None, window=180
):
    snap = CatalogSnapshot(
        tables=tables,
        activity=Activity(
            table_reads=reads or {},
            table_writes=writes or {},
            path_reads=paths or {},
            earliest_event=at(390),
        ),
    )
    analyzer = Analyzer(
        snap, [(storage, list(blobs))], reference=REFERENCE, window_days=window, rates=rates
    )
    return analyzer.run(), analyzer


def test_recent_read_means_no_finding():
    findings, _ = run(
        [table("m.s.t", "t")], [blob("t/p.parquet", accessed=1)], reads={"m.s.t": at(3)}
    )
    assert findings == []


def test_silent_on_both_signals_is_high_confidence_with_cost():
    rates = Rates(per_gb_month={"Hot": 0.02})
    findings, _ = run(
        [table("m.s.t", "t")],
        [blob("t/p.parquet", gb=100, accessed=300)],
        reads={"m.s.t": at(300)},
        rates=rates,
    )
    (f,) = findings
    assert (f.kind, f.reading, f.confidence) == ("unused_table", "cost", "high")
    assert f.monthly_cost == 2.0 and f.currency == "USD"
    assert f.proof_hash.startswith("sha256:")
    assert any("Hot to Cool" in f.recommendation for _ in [0])


def test_storage_read_overrides_lineage_silence():
    findings, _ = run([table("m.s.t", "t")], [blob("t/p.parquet", accessed=10)])
    assert findings == []


def test_without_access_tracking_confidence_is_medium():
    findings, _ = run([table("m.s.t", "t")], [blob("t/p.parquet", accessed=10)], storage=UNTRACKED)
    (f,) = findings
    assert f.confidence == "medium"
    assert any("Last access time tracking is off" in n for n in f.coverage_notes)


def test_path_read_counts_as_table_read():
    findings, _ = run(
        [table("m.s.t", "t")],
        [blob("t/p.parquet", accessed=300)],
        paths={f"{LOC}/t/p.parquet": at(5)},
    )
    assert findings == []


def test_new_tables_and_views_are_skipped():
    findings, _ = run([table("m.s.new", "new", created=10), table("m.s.v", None, ttype="VIEW")])
    assert findings == []


def test_still_fed_table_is_flagged():
    (f,) = run([table("m.s.t", "t")], [blob("t/p.parquet", accessed=300)], writes={"m.s.t": at(0)})[
        0
    ]
    assert f.details["still_fed"] is True
    assert "still writes" in f.recommendation


def test_personal_columns_add_a_compliance_finding():
    findings, _ = run(
        [table("m.s.clientes", "c", columns=["cpf", "email", "valor"])],
        [blob("c/p.parquet", accessed=300)],
    )
    readings = sorted(f.reading for f in findings)
    assert readings == ["compliance", "cost"]
    compliance = next(f for f in findings if f.reading == "compliance")
    assert set(compliance.details["personal_columns"]) == {"cpf", "email"}


def test_orphan_storage_groups_and_path_reads():
    blobs = [
        blob("exports/a/x1.parquet", accessed=400, modified=700),
        blob("exports/a/x2.parquet", accessed=400, modified=700),
        blob("exports/b/y.parquet", accessed=400, modified=700),
        blob("exports/fresh/z.parquet", modified=5),
    ]
    findings, _ = run([], blobs, paths={f"{LOC}/exports/b": at(2)})
    assert [f.asset for f in findings] == [f"{LOC}/exports/a"]
    assert findings[0].confidence == "medium"
    assert findings[0].details["files"] == 2


def test_no_rates_means_no_cost_and_a_note():
    (f,) = run([table("m.s.t", "t")], [blob("t/p.parquet", accessed=300)])[0]
    assert f.monthly_cost is None
    assert any("No storage rates" in n for n in f.coverage_notes)


def test_long_window_and_short_history_are_noted():
    _, analyzer = run([], window=500)
    assert any("longer than the lineage history" in n for n in analyzer.notes)
    assert any("Lineage history starts" in n for n in analyzer.notes)


def test_proof_hash_is_stable_and_sensitive():
    args = ([table("m.s.t", "t")], [blob("t/p.parquet", accessed=300)])
    (a,) = run(*args)[0]
    (b,) = run(*args)[0]
    (c,) = run([table("m.s.t", "t")], [blob("t/p.parquet", accessed=301)])[0]
    assert a.proof_hash == b.proof_hash != c.proof_hash


def _producers(writes, reads_by):
    from cosmosproof.producers import ProducerActivity

    return ProducerActivity(writes=writes, reads_by=reads_by)


def test_intermediate_table_of_a_used_job_is_not_flagged():
    # job:a reads bronze to build gold; a dashboard ("other") reads gold.
    tables = [table("m.s.bronze", None), table("m.s.gold", None)]
    producers = _producers(
        writes={"job:a": {"m.s.bronze": at(1), "m.s.gold": at(1)}},
        reads_by={"m.s.bronze": {"job:a": at(1)}, "m.s.gold": {"other": at(2)}},
    )
    snap = CatalogSnapshot(tables=tables, activity=Activity(earliest_event=at(390)))
    findings = Analyzer(snap, [], reference=REFERENCE, window_days=180, producers=producers).run()
    assert findings == []


def test_chain_of_dead_producers():
    # job:a feeds t1; job:b reads t1 to feed t2; nobody reads t2. Both are dead.
    tables = [table("m.s.t1", None), table("m.s.t2", None)]
    producers = _producers(
        writes={"job:a": {"m.s.t1": at(1)}, "job:b": {"m.s.t2": at(1)}},
        reads_by={"m.s.t1": {"job:b": at(1)}},
    )
    snap = CatalogSnapshot(tables=tables, activity=Activity(earliest_event=at(390)))
    findings = Analyzer(snap, [], reference=REFERENCE, window_days=180, producers=producers).run()
    kinds = sorted((f.kind, f.asset) for f in findings)
    assert kinds == [
        ("unused_producer", "job a"),
        ("unused_producer", "job b"),
        ("unused_table", "m.s.t1"),
        ("unused_table", "m.s.t2"),
    ]
