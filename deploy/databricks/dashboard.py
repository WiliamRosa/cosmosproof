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


def _counter(name: str, dataset: str, expression: str, title: str, x: int) -> dict:
    return {
        "widget": {
            "name": name,
            "queries": [
                {
                    "name": "main_query",
                    "query": {
                        "datasetName": dataset,
                        "fields": [_field("value", expression)],
                        "disaggregated": False,
                    },
                }
            ],
            "spec": {
                "version": 2,
                "widgetType": "counter",
                "encodings": {"value": {"fieldName": "value", "displayName": title}},
                "frame": {"showTitle": True, "title": title},
            },
        },
        "position": {"x": x, "y": 1, "width": 2, "height": 3},
    }


def _table(name: str, dataset: str, columns: list[tuple[str, str]], title: str, y: int) -> dict:
    return {
        "widget": {
            "name": name,
            "queries": [
                {
                    "name": "main_query",
                    "query": {
                        "datasetName": dataset,
                        "fields": [_field(c) for c, _ in columns],
                        "disaggregated": True,
                    },
                }
            ],
            "spec": {
                "version": 1,
                "widgetType": "table",
                "encodings": {
                    "columns": [{"fieldName": c, "displayName": label} for c, label in columns]
                },
                "frame": {"showTitle": True, "title": title},
            },
        },
        "position": {"x": 0, "y": y, "width": 6, "height": 7},
    }


def dashboard(schema: str) -> dict:
    datasets = [
        {
            "name": "latest",
            "displayName": "Latest findings",
            "queryLines": [
                "SELECT reading, kind, asset, owner, confidence, status, monthly_cost, currency, ",
                "ROUND(size_bytes / 1024 / 1024, 1) AS size_mb, recommendation, evidence, ",
                "coverage_notes, proof_hash ",
                f"FROM {schema}.latest WHERE status <> 'resolved' ",
                "ORDER BY monthly_cost DESC NULLS LAST",
            ],
        },
        {
            "name": "changes",
            "displayName": "Changes since the previous run",
            "queryLines": [
                "SELECT status, reading, kind, asset, owner, confidence, monthly_cost, currency ",
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
        ("size_mb", "Size (MB)"),
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
                        "What in this workspace costs money, creates risk or holds personal data "
                        "without being used, with the evidence behind each finding. "
                        "CosmosProof only reads; every action is a person's decision.",
                    ]
                },
            },
            "position": {"x": 0, "y": 0, "width": 6, "height": 1},
        },
        _counter("open", "latest", "COUNT(`asset`)", "Open findings", 0),
        _counter(
            "cost", "latest", "SUM(`monthly_cost`)", "Monthly cost (list prices / your rates)", 2
        ),
        _counter("new", "changes", "COUNT_IF(`status` = 'new')", "New since the previous run", 4),
        {
            "widget": {
                "name": "by_reading",
                "queries": [
                    {
                        "name": "main_query",
                        "query": {
                            "datasetName": "latest",
                            "fields": [_field("reading"), _field("findings", "COUNT(`asset`)")],
                            "disaggregated": False,
                        },
                    }
                ],
                "spec": {
                    "version": 3,
                    "widgetType": "bar",
                    "encodings": {
                        "x": {
                            "fieldName": "reading",
                            "scale": {"type": "categorical"},
                            "displayName": "Reading",
                        },
                        "y": {
                            "fieldName": "findings",
                            "scale": {"type": "quantitative"},
                            "displayName": "Findings",
                        },
                    },
                    "frame": {"showTitle": True, "title": "Findings by reading"},
                },
            },
            "position": {"x": 0, "y": 4, "width": 3, "height": 5},
        },
        {
            "widget": {
                "name": "over_time",
                "queries": [
                    {
                        "name": "main_query",
                        "query": {
                            "datasetName": "runs",
                            "fields": [_field("generated_ts"), _field("open_findings")],
                            "disaggregated": True,
                        },
                    }
                ],
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
                    "frame": {"showTitle": True, "title": "Open findings over time"},
                },
            },
            "position": {"x": 3, "y": 4, "width": 3, "height": 5},
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
            ],
            "New and resolved since the previous run",
            9,
        ),
        _table("findings_table", "latest", columns, "Open findings with evidence", 16),
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
