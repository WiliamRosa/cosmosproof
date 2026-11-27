import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _module():
    spec = importlib.util.spec_from_file_location(
        "dashboard", ROOT / "deploy" / "databricks" / "dashboard.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_layout_fits_the_grid_without_overlaps():
    layout = _module().dashboard("c.s")["pages"][0]["layout"]
    cells = set()
    for item in layout:
        pos = item["position"]
        assert pos["x"] + pos["width"] <= 6
        for x in range(pos["x"], pos["x"] + pos["width"]):
            for y in range(pos["y"], pos["y"] + pos["height"]):
                assert (x, y) not in cells, item["widget"]["name"]
                cells.add((x, y))


def test_tables_carry_the_full_column_definition():
    layout = _module().dashboard("c.s")["pages"][0]["layout"]
    tables = [
        i["widget"] for i in layout if i["widget"].get("spec", {}).get("widgetType") == "table"
    ]
    assert len(tables) == 2
    for table in tables:
        fields = {f["name"] for f in table["queries"][0]["query"]["fields"]}
        for column in table["spec"]["encodings"]["columns"]:
            assert column["fieldName"] in fields
            assert {"type", "displayAs", "visible", "order", "title"} <= column.keys()


def test_every_widget_reads_a_declared_dataset():
    board = _module().dashboard("c.s")
    names = {d["name"] for d in board["datasets"]}
    for item in board["pages"][0]["layout"]:
        for query in item["widget"].get("queries", []):
            assert query["query"]["datasetName"] in names
