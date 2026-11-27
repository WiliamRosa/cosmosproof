"""Generates the grants a customer gives CosmosProof's identity (ADR 0003).

CosmosProof never runs these: a person reviews and runs them. The output is plain text, so a
security team can read every line before anything changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

INVENTORY_FIELDS = [
    "Name",
    "Creation-Time",
    "Last-Modified",
    "LastAccessTime",
    "Content-Length",
    "AccessTier",
    "hdi_isfolder",
]
SYSTEM_SCHEMAS = ["access", "lakeflow", "billing"]


@dataclass
class StorageAccount:
    resource_group: str
    name: str

    @classmethod
    def parse(cls, value: str) -> StorageAccount:
        group, sep, name = value.partition("/")
        if not sep or not group or not name:
            raise ValueError(f"expected <resource-group>/<account>, got {value!r}")
        return cls(group, name)


def inventory_policy(container: str, schedule: str = "weekly") -> dict:
    return {
        "enabled": True,
        "rules": [
            {
                "enabled": True,
                "name": "cosmosproof",
                "destination": container,
                "definition": {
                    "filters": {"blobTypes": ["blockBlob"]},
                    "format": "csv",
                    "objectType": "blob",
                    "schedule": schedule,
                    "schemaFields": INVENTORY_FIELDS,
                },
            }
        ],
    }


def databricks_grants(application_id: str, catalogs: list[str]) -> str:
    who = f"`{application_id}`"
    lines = [
        "-- The identity must first be added to the workspace as a service principal.",
        "-- Run this part in a Databricks SQL editor as a Databricks ACCOUNT admin: workspace",
        "-- admins and metastore admins get PERMISSION_DENIED on the system catalog.",
        "-- (An Entra ID Global Administrator can sign in at https://accounts.azuredatabricks.net",
        "-- to act as, or appoint, an account admin.)",
        f"GRANT USE CATALOG ON CATALOG system TO {who};",
    ]
    for schema in SYSTEM_SCHEMAS:
        lines.append(f"GRANT USE SCHEMA ON SCHEMA system.{schema} TO {who};")
        lines.append(f"GRANT SELECT ON SCHEMA system.{schema} TO {who};")
    lines.append(
        "-- This part can be run by each catalog's owner. BROWSE lets the identity see table "
        "metadata (names, owners, storage paths, column names) without reading any data."
    )
    lines += [f"GRANT BROWSE ON CATALOG `{c}` TO {who};" for c in catalogs]
    lines.append(
        "-- Also give the identity CAN USE on one SQL warehouse (warehouse > Permissions) and the "
        "Databricks SQL access entitlement (workspace settings > identity)."
    )
    return "\n".join(lines)


def azure_commands(
    object_id: str,
    subscription: str,
    accounts: list[StorageAccount],
    container: str,
    policy_file: str = "cosmosproof-inventory-policy.json",
) -> str:
    lines = [
        "# Run with the Azure CLI as someone who can assign roles on these storage accounts.",
        "# On Git Bash for Windows, prefix with MSYS_NO_PATHCONV=1 so /subscriptions/... paths",
        "# are not rewritten.",
    ]
    for acc in accounts:
        scope = (
            f"/subscriptions/{subscription}/resourceGroups/{acc.resource_group}"
            f"/providers/Microsoft.Storage/storageAccounts/{acc.name}"
        )
        lines += [
            "",
            f"# --- {acc.name} ---",
            "# Read-only access to blobs (the inventory reports). No write role is ever needed.",
            f"az role assignment create --assignee-object-id {object_id} "
            f'--assignee-principal-type ServicePrincipal --role "Storage Blob Data Reader" '
            f"--scope {scope}",
            "# Free; last access times are recorded from now on.",
            f"az storage account blob-service-properties update --account-name {acc.name} "
            f"--resource-group {acc.resource_group} --enable-last-access-tracking true",
            "# The container that receives the inventory reports (management plane: no data "
            "role needed).",
            f"az storage container-rm create --name {container} --storage-account {acc.name} "
            f"--resource-group {acc.resource_group}",
            f"az storage account blob-inventory-policy create --account-name {acc.name} "
            f"--resource-group {acc.resource_group} --policy @{policy_file}",
        ]
    return "\n".join(lines)


def onboarding_script(
    *,
    application_id: str,
    object_id: str,
    subscription: str,
    accounts: list[StorageAccount],
    catalogs: list[str],
    container: str = "cosmosproof-inventory",
    schedule: str = "weekly",
) -> str:
    policy = json.dumps(inventory_policy(container, schedule), indent=2)
    return "\n".join(
        [
            "# CosmosProof onboarding: review every line before running anything.",
            "# CosmosProof itself never runs these commands and never writes to your data.",
            "",
            "## 1. Databricks (SQL)",
            "",
            databricks_grants(application_id, catalogs),
            "",
            "## 2. Azure storage (shell)",
            "",
            azure_commands(object_id, subscription, accounts, container),
            "",
            "## 3. Inventory policy (save as cosmosproof-inventory-policy.json)",
            "",
            "# hdi_isfolder exists only on accounts with hierarchical namespace (ADLS Gen2);",
            "# remove it for plain Blob Storage accounts.",
            policy,
            "",
        ]
    )
