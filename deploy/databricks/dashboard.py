"""Creates the Unity Catalog views and the AI/BI dashboard over published CosmosProof runs.

    DATABRICKS_TOKEN=... python deploy/databricks/dashboard.py --host adb-....azuredatabricks.net \
        --warehouse-id <id> --publish abfss://<container>@<account>.dfs.core.windows.net/<path> \
        --schema <catalog>.<schema>

Prerequisite: a Unity Catalog external location over the publish location, readable by the
people who will see the dashboard (findings name owners and internal assets). Run it after the
first published scan, so the findings folder exists. Idempotent.
Needs the `databricks` extra.
"""

from __future__ import annotations

import argparse
import json
import os

# Explicit schema: read_files cannot infer one from empty files (a run with no findings).
SCHEMA = (
    "run_id STRING, generated_at STRING, reference_date STRING, window_days INT, status STRING, "
    "id STRING, reading STRING, kind STRING, asset STRING, owner STRING, size_bytes BIGINT, "
    "monthly_cost DOUBLE, currency STRING, confidence STRING, recommendation STRING, "
    "evidence STRING, coverage_notes STRING, proof_hash STRING"
)
RUN_SCHEMA = (
    "run_id STRING, generated_at STRING, reference_date STRING, window_days INT, "
    "open_findings INT, new_findings INT, ongoing_findings INT, resolved_findings INT, "
    "monthly_cost DOUBLE, currency STRING, storage_files BIGINT, coverage_notes STRING"
)
NAME = "CosmosProof"


def views(publish: str, schema: str) -> list[str]:
    url = publish.rstrip("/")
    return [
        f"CREATE SCHEMA IF NOT EXISTS {schema}",
        f"""CREATE OR REPLACE VIEW {schema}.findings AS
            SELECT *, to_timestamp(generated_at) AS generated_ts
            FROM read_files('{url}/findings/', format => 'json', schema => '{SCHEMA}')""",
        # One row per run, so runs with no findings still show.
        f"""CREATE OR REPLACE VIEW {schema}.runs AS
            SELECT *, to_timestamp(generated_at) AS generated_ts
            FROM read_files('{url}/summaries/', format => 'json', schema => '{RUN_SCHEMA}')""",
        # The latest run comes from the summaries: a latest run with no findings must show none,
        # not the previous run's findings.
        f"""CREATE OR REPLACE VIEW {schema}.latest AS
            SELECT * FROM {schema}.findings
            WHERE run_id = (SELECT MAX(run_id) FROM {schema}.runs)""",
    ]


def _field(name: str, expression: str | None = None) -> dict:
    return {"name": name, "expression": expression or f"`{name}`"}


def _query(dataset: str, fields: list[dict], disaggregated: bool) -> list[dict]:
    return [
        {
            "name": "main_query",
            "query": {"datasetName": dataset, "fields": fields, "disaggregated": disaggregated},
        }
    ]


def _position(x: int, y: int, width: int, height: int) -> dict:
    return {"x": x, "y": y, "width": width, "height": height}


def _counter(name: str, dataset: str, expression: str, title: str, x: int, y: int) -> dict:
    return {
        "widget": {
            "name": name,
            "queries": _query(dataset, [_field("value", expression)], False),
            "spec": {
                "version": 2,
                "widgetType": "counter",
                "encodings": {"value": {"fieldName": "value", "displayName": title}},
                "frame": {"showTitle": True, "title": title},
            },
        },
        "position": _position(x, y, 1, 2),
    }


def _bar(name, dataset, x_field, x_label, y_field, y_expr, y_label, title, pos, color=None):
    fields = [_field(x_field), _field(y_field, y_expr)]
    encodings = {
        "x": {"fieldName": x_field, "scale": {"type": "categorical"}, "displayName": x_label},
        "y": {"fieldName": y_field, "scale": {"type": "quantitative"}, "displayName": y_label},
    }
    if color:
        fields.append(_field(color[0]))
        encodings["color"] = {
            "fieldName": color[0],
            "scale": {"type": "categorical"},
            "displayName": color[1],
        }
    return {
        "widget": {
            "name": name,
            "queries": _query(dataset, fields, False),
            "spec": {
                "version": 3,
                "widgetType": "bar",
                "encodings": encodings,
                "frame": {"showTitle": True, "title": title},
            },
        },
        "position": pos,
    }


# The table widget needs the full column definition; with only a field name and a display name
# the dashboard shows "Invalid widget definition".
NUMBER_COLUMNS = {"monthly_cost", "size_gb"}


def _column(field: str, title: str, order: int) -> dict:
    number = field in NUMBER_COLUMNS
    column = {
        "fieldName": field,
        "booleanValues": ["false", "true"],
        "imageUrlTemplate": "{{ @ }}",
        "imageTitleTemplate": "{{ @ }}",
        "imageWidth": "",
        "imageHeight": "",
        "linkUrlTemplate": "{{ @ }}",
        "linkTextTemplate": "{{ @ }}",
        "linkTitleTemplate": "{{ @ }}",
        "linkOpenInNewTab": True,
        "type": "float" if number else "string",
        "displayAs": "number" if number else "string",
        "visible": True,
        "order": 100000 + order,
        "title": title,
        "allowSearch": not number,
        "alignContent": "right" if number else "left",
        "allowHTML": False,
        "highlightLinks": False,
        "useMonospaceFont": field == "proof_hash",
        "preserveWhitespace": field in {"evidence", "coverage_notes"},
        "displayName": title,
    }
    if number:
        column["numberFormat"] = "0.00"
    return column


def _table(name: str, dataset: str, columns: list[tuple[str, str]], title: str, pos: dict) -> dict:
    return {
        "widget": {
            "name": name,
            "queries": _query(dataset, [_field(c) for c, _ in columns], True),
            "spec": {
                "version": 1,
                "widgetType": "table",
                "encodings": {
                    "columns": [_column(c, label, i) for i, (c, label) in enumerate(columns)]
                },
                "invisibleColumns": [],
                "allowHTMLByDefault": False,
                "itemsPerPage": 25,
                "paginationSize": "default",
                "condensed": True,
                "withRowNumber": False,
                "frame": {"showTitle": True, "title": title},
            },
        },
        "position": pos,
    }


def dashboard(schema: str) -> dict:
    datasets = [
        {
            "name": "latest",
            "displayName": "Open findings",
            "queryLines": [
                "SELECT reading, kind, asset, coalesce(owner, 'unknown') AS owner, confidence, ",
                "status, monthly_cost, currency, ",
                "ROUND(size_bytes / 1024 / 1024 / 1024, 2) AS size_gb, recommendation, evidence, ",
                # A compliance finding repeats the size of its table's cost finding.
                "CASE WHEN reading = 'cost' THEN ROUND(size_bytes / 1024 / 1024 / 1024, 2) END ",
                "AS cost_size_gb, ",
                "coverage_notes, proof_hash ",
                f"FROM {schema}.latest WHERE status <> 'resolved' ",
                "ORDER BY monthly_cost DESC NULLS LAST",
            ],
        },
        {
            "name": "changes",
            "displayName": "Changes since the previous run",
            "queryLines": [
                "SELECT status, reading, kind, asset, coalesce(owner, 'unknown') AS owner, ",
                "confidence, monthly_cost, currency ",
                f"FROM {schema}.latest WHERE status IN ('new', 'resolved')",
            ],
        },
        {
            "name": "runs",
            "displayName": "Runs",
            "queryLines": [f"SELECT * FROM {schema}.runs ORDER BY generated_ts"],
        },
    ]
    columns = [
        ("reading", "Reading"),
        ("kind", "Kind"),
        ("asset", "Asset"),
        ("owner", "Owner"),
        ("confidence", "Confidence"),
        ("status", "Status"),
        ("monthly_cost", "Monthly cost"),
        ("currency", "Currency"),
        ("size_gb", "Size (GB)"),
        ("recommendation", "Recommendation"),
        ("evidence", "Evidence"),
        ("coverage_notes", "What could not be seen"),
        ("proof_hash", "Proof"),
    ]
    layout = [
        {
            "widget": {
                "name": "title",
                "multilineTextboxSpec": {
                    "lines": [
                        "## CosmosProof\n",
                        "\n",
                        "What in this workspace **costs money, creates risk or holds personal "
                        "data without being used**, with the evidence behind each finding. "
                        "Costs use your storage rates and Databricks list prices. CosmosProof "
                        "only reads: every action is a person's decision.\n",
                    ]
                },
            },
            "position": _position(0, 0, 6, 2),
        },
        _counter("open", "latest", "COUNT(`asset`)", "Open findings", 0, 2),
        _counter("cost", "latest", "SUM(`monthly_cost`)", "Estimated monthly cost", 1, 2),
        _counter("storage", "latest", "SUM(`cost_size_gb`)", "Unused storage (GB)", 2, 2),
        _counter(
            "personal",
            "latest",
            "COUNT_IF(`reading` = 'compliance')",
            "Personal data at rest (LGPD)",
            3,
            2,
        ),
        _counter("new", "changes", "COUNT_IF(`status` = 'new')", "New since last run", 4, 2),
        _counter(
            "resolved",
            "changes",
            "COUNT_IF(`status` = 'resolved')",
            "Resolved since last run",
            5,
            2,
        ),
        _bar(
            "by_reading",
            "latest",
            "reading",
            "Reading",
            "findings",
            "COUNT(`asset`)",
            "Findings",
            "Findings by reading and confidence",
            _position(0, 4, 2, 6),
            color=("confidence", "Confidence"),
        ),
        _bar(
            "by_owner",
            "latest",
            "owner",
            "Owner",
            "cost",
            "SUM(`monthly_cost`)",
            "Monthly cost",
            "Monthly cost by owner",
            _position(2, 4, 2, 6),
        ),
        {
            "widget": {
                "name": "over_time",
                "queries": _query("runs", [_field("generated_ts"), _field("open_findings")], True),
                "spec": {
                    "version": 3,
                    "widgetType": "line",
                    "encodings": {
                        "x": {
                            "fieldName": "generated_ts",
                            "scale": {"type": "temporal"},
                            "displayName": "Run",
                        },
                        "y": {
                            "fieldName": "open_findings",
                            "scale": {"type": "quantitative"},
                            "displayName": "Open findings",
                        },
                    },
                    "frame": {"showTitle": True, "title": "Open findings per run"},
                },
            },
            "position": _position(4, 4, 2, 6),
        },
        _table(
            "changes_table",
            "changes",
            [
                ("status", "Status"),
                ("reading", "Reading"),
                ("kind", "Kind"),
                ("asset", "Asset"),
                ("owner", "Owner"),
                ("confidence", "Confidence"),
                ("monthly_cost", "Monthly cost"),
                ("currency", "Currency"),
            ],
            "New and resolved since the last run",
            _position(0, 10, 6, 5),
        ),
        _table(
            "findings_table",
            "latest",
            columns,
            "Open findings with evidence",
            _position(0, 15, 6, 10),
        ),
    ]
    return {
        "datasets": datasets,
        "pages": [
            {
                "name": "overview",
                "displayName": "Overview",
                "pageType": "PAGE_TYPE_CANVAS",
                "layout": layout,
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--publish", required=True)
    parser.add_argument("--schema", required=True, help="<catalog>.<schema> for the views")
    parser.add_argument("--name", default=NAME, help="Dashboard name")
    args = parser.parse_args()
    token = os.environ["DATABRICKS_TOKEN"]

    from databricks import sql
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.dashboards import Dashboard

    con = sql.connect(
        server_hostname=args.host,
        http_path=f"/sql/1.0/warehouses/{args.warehouse_id}",
        access_token=token,
    )
    with con.cursor() as cur:
        for statement in views(args.publish, args.schema):
            cur.execute(statement)
        for dataset in dashboard(args.schema)["datasets"]:
            cur.execute("".join(dataset["queryLines"]))
            print(f"dataset {dataset['name']}: {len(cur.fetchall())} rows")
    con.close()

    w = WorkspaceClient(host=f"https://{args.host}", token=token)
    parent = f"/Users/{w.current_user.me().user_name}"
    body = Dashboard(
        display_name=args.name,
        warehouse_id=args.warehouse_id,
        parent_path=parent,
        serialized_dashboard=json.dumps(dashboard(args.schema)),
    )
    existing = next((d for d in w.lakeview.list() if d.display_name == args.name), None)
    if existing:
        created = w.lakeview.update(dashboard_id=existing.dashboard_id, dashboard=body)
    else:
        created = w.lakeview.create(dashboard=body)
    w.lakeview.publish(
        dashboard_id=created.dashboard_id, warehouse_id=args.warehouse_id, embed_credentials=True
    )
    print(f"dashboard: https://{args.host}/dashboardsv3/{created.dashboard_id}/published")


if __name__ == "__main__":
    main()
