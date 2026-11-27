"""Reads Azure Blob Inventory reports (CSV or Parquet) for ADLS Gen2 containers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import pyarrow.parquet as pq

# Inventory field names as Azure writes them, lower-cased for matching.
_NAME = "name"
_SIZE = "content-length"
_TIER = "accesstier"
_MODIFIED = "last-modified"
_ACCESSED = "lastaccesstime"
_FOLDER = "hdi_isfolder"


@dataclass
class Blob:
    url: str
    size: int
    tier: str | None
    last_modified: datetime | None
    last_access: datetime | None


def container_url(account: str, container: str) -> str:
    return f"abfss://{container}@{account}.dfs.core.windows.net/"


def parse_time(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        # Azure writes up to 7 fractional digits; Python reads at most 6.
        if "." in text:
            head, rest = text.split(".", 1)
            digits = "".join(ch for ch in rest if ch.isdigit())
            tail = rest[len(digits) :]
            text = f"{head}.{digits[:6]}{tail}"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _rows(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() == ".parquet":
        return pq.read_table(path).to_pylist()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def read_inventory(path: str | Path, account: str, container: str) -> list[Blob]:
    base = container_url(account, container)
    blobs: list[Blob] = []
    for raw in _rows(Path(path)):
        row = {str(k).strip().lower(): v for k, v in raw.items()}
        name = str(row.get(_NAME) or "").strip("/")
        if not name or str(row.get(_FOLDER, "")).lower() == "true":
            continue
        size = row.get(_SIZE)
        blobs.append(
            Blob(
                url=base + name,
                size=int(size) if size not in (None, "") else 0,
                tier=(str(row[_TIER]) if row.get(_TIER) not in (None, "") else None),
                last_modified=parse_time(row.get(_MODIFIED)),
                last_access=parse_time(row.get(_ACCESSED)),
            )
        )
    return blobs
