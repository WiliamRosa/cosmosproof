"""The scan configuration file (cosmosproof.yml)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from cosmos_semantic.connectors import DataSourceConfig, _expand_env
from pydantic import BaseModel, ConfigDict, Field


class SystemTables(BaseModel):
    """Where to read Unity Catalog metadata. Overridable so tests (or a customer's own views)
    can stand in for the system tables."""

    model_config = ConfigDict(extra="forbid")

    lineage: str = "system.access.table_lineage"
    tables: str = "system.information_schema.tables"
    columns: str = "system.information_schema.columns"
    jobs: str = "system.lakeflow.jobs"
    pipelines: str = "system.lakeflow.pipelines"
    billing_usage: str = "system.billing.usage"
    list_prices: str = "system.billing.list_prices"


class DatabricksConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: DataSourceConfig
    system_tables: SystemTables = SystemTables()
    producers: bool = Field(
        True, description="Analyze jobs and pipelines that feed tables nobody reads (phase 2)."
    )


class StorageConfig(BaseModel):
    """One ADLS Gen2 container and its Blob Inventory report."""

    model_config = ConfigDict(extra="forbid")

    account: str
    container: str
    inventory: str | None = Field(
        None,
        description="Path to a Blob Inventory report file (CSV or Parquet) for this container.",
    )
    access_tracking_since: date | None = Field(
        None,
        description=(
            "Date last access time tracking was enabled on the storage account. Empty when it is "
            "disabled; last access is then ignored."
        ),
    )


class Rates(BaseModel):
    """Storage price per GB-month for each access tier. Use the prices of your own agreement:
    there are no built-in defaults, because a wrong price is worse than no price."""

    model_config = ConfigDict(extra="forbid")

    currency: str = "USD"
    per_gb_month: dict[str, float] = {}


class ScanConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_days: int = Field(180, ge=1, description="No read in this many days means unused.")
    reference_date: date | None = None
    orphan_depth: int = Field(
        2, ge=1, description="Directory depth used to group storage not owned by any table."
    )
    exclude_catalogs: list[str] = Field(
        ["samples"], description="Catalogs to ignore; `samples` holds Databricks example datasets."
    )
    databricks: DatabricksConfig | None = None
    storage: list[StorageConfig] = []
    rates: Rates | None = None


def load_config(path: str | Path) -> ScanConfig:
    with Path(path).open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return ScanConfig.model_validate(_expand_env(raw))
