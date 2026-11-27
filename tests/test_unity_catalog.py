from conftest import LOC, NAMES, REFERENCE

from cosmosproof.unity_catalog import read_catalog


def test_reads_tables_columns_and_activity(duck):
    snap = read_catalog(duck, NAMES, REFERENCE)
    names = {t.full_name for t in snap.tables}
    assert names == {
        "main.raw.clientes",
        "main.silver.contas",
        "main.gold.kpi_view",
        "samples.tpch.orders",
    }
    samples = next(t for t in snap.tables if t.full_name == "samples.tpch.orders")
    assert samples.storage_path is None  # empty string from managed tables becomes None
    clientes = next(t for t in snap.tables if t.full_name == "main.raw.clientes")
    assert clientes.columns == ["cpf", "valor"]
    assert clientes.owner == "legado"
    assert clientes.storage_path == f"{LOC}/raw/clientes"

    act = snap.activity
    assert act.table_reads["main.silver.contas"].isoformat().startswith("2026-11-25")
    assert act.table_read_counts["main.silver.contas"] == 2  # the 2024 event is outside history
    assert act.table_writes["main.raw.clientes"].isoformat().startswith("2026-11-25")
    assert f"{LOC}/exports/x" in act.path_reads
    assert act.earliest_event.isoformat().startswith("2026-01-10")
