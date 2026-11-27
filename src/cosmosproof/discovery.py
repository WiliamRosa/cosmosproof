"""Discovers the Azure Databricks workspaces and ADLS Gen2 accounts the identity can see
(ADR 0010), suggests an environment for each, and enriches workspaces with what they use.

Read-only: Azure Resource Graph for the inventory, each workspace's REST API for its
warehouses, catalogs and external locations.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import asdict, dataclass, field

ARM = "https://management.azure.com"
GRAPH_QUERY = (
    "Resources"
    " | where type =~ 'microsoft.databricks/workspaces'"
    " or (type =~ 'microsoft.storage/storageaccounts' and properties.isHnsEnabled == true)"
    " | project id, name, type, resourceGroup, subscriptionId, location, tags,"
    " workspaceUrl = tostring(properties.workspaceUrl), sku = tostring(sku.name)"
)
ENV_TAGS = ("env", "environment", "ambiente", "stage")
# Order matters: the first match wins, so "prod-poc" is treated as non-production.
ENV_PATTERNS = [
    ("poc", r"(^|[-_.])(poc|pov|sandbox|sbx|lab|demo|trial)([-_.0-9]|$)"),
    ("dev", r"(^|[-_.])(dev|develop|development|desenv)([-_.0-9]|$)"),
    ("test", r"(^|[-_.])(test|tst|qa|hml|homolog|uat|stg|staging)([-_.0-9]|$)"),
    ("prod", r"(^|[-_.])(prod|prd|production|producao)([-_.0-9]|$)"),
]
SELECTED_BY_DEFAULT = {"prod", "unknown"}


@dataclass
class Resource:
    id: str
    kind: str  # "workspace" or "storage"
    name: str
    subscription: str
    resource_group: str
    location: str
    tags: dict[str, str] = field(default_factory=dict)
    environment: str = "unknown"
    environment_source: str = "none"  # "tag", "name" or "none"
    host: str | None = None  # workspaces only
    warehouses: list[dict] = field(default_factory=list)
    catalogs: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)  # abfss:// URLs of external locations
    status: str = "discovered"  # discovered, ready, error
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def suggest_environment(name: str, tags: dict[str, str]) -> tuple[str, str]:
    """Returns (environment, source). Tags win over names; a person always has the final say."""
    lowered = {k.lower(): str(v).lower() for k, v in (tags or {}).items()}
    for key in ENV_TAGS:
        if key in lowered:
            value = lowered[key]
            for env, pattern in ENV_PATTERNS:
                if re.search(pattern, value) or value == env:
                    return env, "tag"
            return "unknown", "tag"
    for env, pattern in ENV_PATTERNS:
        if re.search(pattern, name.lower()):
            return env, "name"
    return "unknown", "none"


def selected_by_default(resource: Resource) -> bool:
    return resource.environment in SELECTED_BY_DEFAULT


def parse_graph_rows(rows: list[dict]) -> list[Resource]:
    out = []
    for row in rows:
        kind = "workspace" if "databricks" in row["type"].lower() else "storage"
        env, source = suggest_environment(row["name"], row.get("tags") or {})
        out.append(
            Resource(
                id=row["id"],
                kind=kind,
                name=row["name"],
                subscription=row["subscriptionId"],
                resource_group=row["resourceGroup"],
                location=row["location"],
                tags=row.get("tags") or {},
                environment=env,
                environment_source=source,
                host=row.get("workspaceUrl") or None,
            )
        )
    return sorted(out, key=lambda r: (r.kind, r.name))


def _post_json(url: str, token: str, body: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 (fixed host)
        return json.loads(response.read())


def _get_json(url: str, token: str) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (workspace host)
        return json.loads(response.read())


def query_graph(
    token: str,
    subscriptions: list[str] | None = None,
    management_groups: list[str] | None = None,
) -> list[Resource]:
    """Without a scope, Resource Graph covers every subscription the identity can read."""
    body: dict = {"query": GRAPH_QUERY, "options": {"resultFormat": "objectArray", "$top": 1000}}
    if subscriptions:
        body["subscriptions"] = subscriptions
    if management_groups:
        body["managementGroups"] = management_groups
    rows: list[dict] = []
    while True:
        page = _post_json(
            f"{ARM}/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01", token, body
        )
        rows.extend(page.get("data", []))
        skip = page.get("$skipToken")
        if not skip:
            break
        body["options"]["$skipToken"] = skip
    return parse_graph_rows(rows)


def pick_warehouse(warehouses: list[dict]) -> dict | None:
    """Prefer serverless, then running, then the smallest."""
    sizes = ["2X-Small", "X-Small", "Small", "Medium", "Large", "X-Large", "2X-Large"]

    def rank(w: dict) -> tuple:
        size = w.get("cluster_size")
        return (
            not w.get("enable_serverless_compute", False),
            w.get("state") != "RUNNING",
            sizes.index(size) if size in sizes else len(sizes),
        )

    return min(warehouses, key=rank) if warehouses else None


def enrich_workspace(resource: Resource, token: str) -> Resource:
    """Warehouses, catalogs and external locations of one workspace. Never raises: a workspace
    the identity cannot reach is reported, not fatal."""
    base = f"https://{resource.host}"
    try:
        warehouses = _get_json(f"{base}/api/2.0/sql/warehouses", token).get("warehouses", [])
        resource.warehouses = [
            {
                "id": w["id"],
                "name": w.get("name"),
                "cluster_size": w.get("cluster_size"),
                "state": w.get("state"),
                "enable_serverless_compute": w.get("enable_serverless_compute", False),
            }
            for w in warehouses
        ]
        catalogs = _get_json(f"{base}/api/2.1/unity-catalog/catalogs", token).get("catalogs", [])
        resource.catalogs = sorted(
            c["name"]
            for c in catalogs
            if c.get("catalog_type") not in {"SYSTEM_CATALOG", "FOREIGN_CATALOG"}
        )
        locations = _get_json(f"{base}/api/2.1/unity-catalog/external-locations", token)
        resource.locations = sorted(
            loc["url"]
            for loc in locations.get("external_locations", [])
            if not loc["name"].startswith("__databricks")
        )
        resource.status = "ready"
    except Exception as exc:  # 401/403 when the identity is not in the workspace yet
        resource.status = "error"
        resource.error = f"{type(exc).__name__}: {exc}"[:300]
    return resource


def storage_used_by(workspaces: list[Resource]) -> dict[str, list[str]]:
    """Storage account name -> workspaces that reach it through external locations."""
    out: dict[str, list[str]] = {}
    for ws in workspaces:
        for url in ws.locations:
            match = re.match(r"abfss://[^@]+@([a-z0-9]+)\.dfs\.", url)
            if match:
                out.setdefault(match.group(1), []).append(ws.name)
    return {k: sorted(set(v)) for k, v in out.items()}
