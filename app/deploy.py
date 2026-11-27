"""Installs or updates the CosmosProof app in a Databricks workspace (ADR 0010).

    DATABRICKS_TOKEN=... python app/deploy.py --host adb-....azuredatabricks.net \
        --volume /Volumes/cosmosproof/audit/files \
        --identity-app-id <client id> --identity-object-id <object id>

Run once by a workspace administrator after the Marketplace deployment. It uploads the app,
creates or updates it, gives the app's own service principal read and write access to the
volume only, and prints the app URL. Needs the `databricks` extra.
"""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path

HERE = Path(__file__).parent
FILES = [
    "app.py",
    "logic.py",
    "ui.py",
    "requirements.txt",
    "logo-light.svg",
    "logo-dark.svg",
    "mark-light.svg",
    "mark-dark.svg",
]
NAME = "cosmosproof"


def manifest(volume: str, app_id: str, object_id: str) -> str:
    return (
        'command: ["streamlit", "run", "app.py"]\n'
        "env:\n"
        f'  - name: COSMOSPROOF_VOLUME\n    value: "{volume}"\n'
        f'  - name: COSMOSPROOF_IDENTITY_APP_ID\n    value: "{app_id}"\n'
        f'  - name: COSMOSPROOF_IDENTITY_OBJECT_ID\n    value: "{object_id}"\n'
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--volume", required=True, help="/Volumes/<catalog>/<schema>/<volume>")
    parser.add_argument("--identity-app-id", default="")
    parser.add_argument("--identity-object-id", default="")
    parser.add_argument("--warehouse-id", help="Only needed to run the volume grants with SQL")
    args = parser.parse_args()

    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.apps import App, AppDeployment
    from databricks.sdk.service.workspace import ImportFormat

    w = WorkspaceClient(host=f"https://{args.host}", token=os.environ["DATABRICKS_TOKEN"])
    folder = f"/Workspace/Users/{w.current_user.me().user_name}/cosmosproof-app"
    w.workspace.mkdirs(folder)
    for name in FILES:
        w.workspace.upload(
            f"{folder}/{name}", io.BytesIO((HERE / name).read_bytes()), format=ImportFormat.AUTO,
            overwrite=True,
        )  # fmt: skip
    w.workspace.upload(
        f"{folder}/app.yaml",
        io.BytesIO(manifest(args.volume, args.identity_app_id, args.identity_object_id).encode()),
        format=ImportFormat.AUTO,
        overwrite=True,
    )

    existing = {a.name for a in w.apps.list()}
    if NAME not in existing:
        w.apps.create_and_wait(
            app=App(
                name=NAME,
                description="CosmosProof: Lakehouse FinOps findings, selection and access",
            )
        )
    app = w.apps.get(NAME)
    print(f"app service principal: {app.service_principal_client_id}")

    catalog, schema, volume = args.volume.removeprefix("/Volumes/").split("/")[:3]
    grants = [
        f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{app.service_principal_client_id}`",
        f"GRANT USE SCHEMA ON SCHEMA `{catalog}`.`{schema}` TO `{app.service_principal_client_id}`",
        f"GRANT READ VOLUME, WRITE VOLUME ON VOLUME `{catalog}`.`{schema}`.`{volume}` "
        f"TO `{app.service_principal_client_id}`",
    ]
    if args.warehouse_id:
        from databricks import sql

        con = sql.connect(
            server_hostname=args.host,
            http_path=f"/sql/1.0/warehouses/{args.warehouse_id}",
            access_token=os.environ["DATABRICKS_TOKEN"],
        )
        with con.cursor() as cur:
            for grant in grants:
                cur.execute(grant)
        con.close()
        print("volume access granted to the app")
    else:
        print("Run these as the volume owner:\n" + ";\n".join(grants) + ";")

    deployment = w.apps.deploy_and_wait(
        app_name=NAME, app_deployment=AppDeployment(source_code_path=folder)
    )
    print(f"deployment: {deployment.status.state}")
    print(f"app: {w.apps.get(NAME).url}")


if __name__ == "__main__":
    main()
