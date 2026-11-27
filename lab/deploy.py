"""Deploys the CosmosProof lab to a Databricks workspace.

    DATABRICKS_TOKEN=... python lab/deploy.py --host adb-....azuredatabricks.net \
        --warehouse-id <id> --lake abfss://<container>@<account>.dfs.core.windows.net/lab

Creates the `cosmosproof_lab` catalog with fictional data (setup.sql), uploads the producer and
consumer SQL to the workspace, creates two daily jobs on the SQL warehouse and runs both once.
Idempotent: jobs are found by name and updated. Needs the `databricks` extra.
"""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path

HERE = Path(__file__).parent
JOBS = {
    "cosmosproof-lab-producer": ("producer.sql", "0 0 8 * * ?"),
    "cosmosproof-lab-consumer": ("consumer.sql", "0 0 9 * * ?"),
}


def statements(sql: str) -> list[str]:
    body = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return [part.strip() for part in body.split(";") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--lake", required=True, help="abfss:// URL under an external location")
    parser.add_argument("--skip-setup", action="store_true")
    args = parser.parse_args()
    token = os.environ["DATABRICKS_TOKEN"]
    lake = args.lake.rstrip("/")

    from databricks import sql
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service import jobs, workspace

    if not args.skip_setup:
        con = sql.connect(
            server_hostname=args.host,
            http_path=f"/sql/1.0/warehouses/{args.warehouse_id}",
            access_token=token,
        )
        with con.cursor() as cur:
            for st in statements((HERE / "setup.sql").read_text(encoding="utf-8")):
                cur.execute(st.replace("${LAKE}", lake))
                print("setup:", " ".join(st.split())[:80])
        con.close()

    w = WorkspaceClient(host=f"https://{args.host}", token=token)
    folder = f"/Users/{w.current_user.me().user_name}/cosmosproof-lab"
    w.workspace.mkdirs(folder)
    existing = {j.settings.name: j.job_id for j in w.jobs.list() if j.settings}
    for name, (file, cron) in JOBS.items():
        path = f"{folder}/{file}"
        content = (HERE / file).read_text(encoding="utf-8").replace("${LAKE}", lake)
        w.workspace.upload(
            path, io.BytesIO(content.encode()), format=workspace.ImportFormat.RAW, overwrite=True
        )
        settings = jobs.JobSettings(
            name=name,
            tags={"project": "cosmosproof-lab"},
            schedule=jobs.CronSchedule(
                quartz_cron_expression=cron,
                timezone_id="UTC",
                pause_status=jobs.PauseStatus.UNPAUSED,
            ),
            tasks=[
                jobs.Task(
                    task_key="run",
                    sql_task=jobs.SqlTask(
                        warehouse_id=args.warehouse_id,
                        file=jobs.SqlTaskFile(path=path, source=jobs.Source.WORKSPACE),
                    ),
                )
            ],
        )
        if name in existing:
            w.jobs.reset(job_id=existing[name], new_settings=settings)
            job_id = existing[name]
        else:
            job_id = w.jobs.create(
                name=settings.name,
                tags=settings.tags,
                schedule=settings.schedule,
                tasks=settings.tasks,
            ).job_id
        print(f"job {name}: {job_id}")
        run = w.jobs.run_now(job_id=job_id).result()
        print(f"  first run: {run.state.result_state}")


if __name__ == "__main__":
    main()
