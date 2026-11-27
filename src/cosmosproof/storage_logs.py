"""Reads blob read events from Azure Storage resource logs (StorageBlobLogs in Log Analytics).

A second storage signal next to last access time: every read is an event with its exact time,
so there is no one-day granularity, and it covers any reader, inside Databricks or not.
Only reads are queried; CosmosProof never reads the files themselves.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from cosmosproof.inventory import container_url, parse_time

READ_OPERATIONS = ("GetBlob", "ReadFile")


def query_text(account: str, container: str, since: datetime) -> str:
    ops = ", ".join(f"'{op}'" for op in READ_OPERATIONS)
    return (
        "StorageBlobLogs"
        f" | where TimeGenerated >= datetime({since.astimezone(UTC).isoformat()})"
        f" | where AccountName == '{account}' and OperationName in ({ops})"
        " | extend path = tostring(parse_url(Uri).Path)"
        f" | where path startswith '/{container}/'"
        " | summarize last_read = max(TimeGenerated), reads = count() by path"
    )


def parse_rows(rows: list[list], account: str, container: str) -> dict[str, datetime]:
    """Maps abfss:// file URLs to their last read."""
    base = container_url(account, container)
    prefix = f"/{container}/"
    out: dict[str, datetime] = {}
    for path, last_read, _count in rows:
        name = urllib.parse.unquote(str(path))[len(prefix) :].strip("/")
        when = parse_time(last_read)
        if name and when:
            url = base + name
            out[url] = max(when, out.get(url, when))
    return out


def read_logs(
    workspace_id: str, account: str, container: str, since: datetime
) -> dict[str, datetime]:
    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential(exclude_interactive_browser_credential=True).get_token(
        "https://api.loganalytics.io/.default"
    )
    request = urllib.request.Request(
        f"https://api.loganalytics.io/v1/workspaces/{workspace_id}/query",
        data=json.dumps({"query": query_text(account, container, since)}).encode(),
        headers={"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 (fixed https host)
        body = json.loads(response.read())
    rows = body["tables"][0]["rows"] if body.get("tables") else []
    return parse_rows(rows, account, container)
