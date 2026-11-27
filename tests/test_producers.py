from conftest import NAMES, REFERENCE

from cosmosproof.producers import outside_reads, read_producers, tables_by_producer


def test_read_producers(duck):
    act = read_producers(duck, NAMES, REFERENCE, window_days=180)
    assert set(act.writes) == {"job:7", "job:8", "pipeline:p1"}
    assert set(act.writes["job:7"]) == {"main.raw.clientes"}
    assert set(act.reads_by["main.raw.clientes"]) == {"other", "job:7"}
    assert outside_reads(act, "job:7", "main.raw.clientes")[0].isoformat().startswith("2026-01-10")
    assert tables_by_producer(act)["main.raw.clientes"] == ["job:7", "job:8"]

    job = act.producers["job:7"]
    assert (job.name, job.owner, job.deleted) == ("carga clientes", "etl@bank", False)
    assert act.producers["job:8"].deleted is True
    assert act.producers["pipeline:p1"].kind_detail == "INGESTION_PIPELINE"

    cost = act.costs["job:7"]
    # 6 DBU at 0.5 before the price change, 4 DBU at 1.0 after; the 2025 usage is outside the window.
    assert (cost.amount, cost.quantity, cost.currency, cost.unit) == (7.0, 10.0, "USD", "DBU")
    assert act.costs["pipeline:p1"].currency is None
    assert any("pipeline:p1" in n for n in act.notes)


def test_missing_billing_grants_become_notes(duck):
    broken = NAMES.model_copy(update={"billing_usage": "no_such_table", "jobs": "no_such_table"})
    act = read_producers(duck, broken, REFERENCE, window_days=180)
    assert act.costs == {}
    assert any("costs are unavailable" in n for n in act.notes)
    assert any("names are unavailable" in n for n in act.notes)
