"""Lists an ADLS Gen2 container directly, as an alternative to waiting for a Blob Inventory
report. Read-only: it only calls List Blobs. Fine for small and medium lakes; inventory
reports are cheaper for large ones."""

from __future__ import annotations

from cosmosproof.inventory import Blob, container_url, parse_time


def list_container(account: str, container: str, prefix: str | None = None) -> list[Blob]:
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import ContainerClient

    client = ContainerClient(
        account_url=f"https://{account}.blob.core.windows.net",
        container_name=container,
        credential=DefaultAzureCredential(exclude_interactive_browser_credential=True),
    )
    base = container_url(account, container)
    blobs: list[Blob] = []
    for item in client.list_blobs(name_starts_with=prefix, include=["metadata"]):
        if (item.metadata or {}).get("hdi_isfolder") == "true":
            continue
        tier = item.blob_tier
        blobs.append(
            Blob(
                url=base + item.name.strip("/"),
                size=int(item.size or 0),
                tier=str(tier.value if hasattr(tier, "value") else tier) if tier else None,
                last_modified=parse_time(item.last_modified),
                last_access=parse_time(getattr(item, "last_accessed_on", None)),
            )
        )
    return blobs
