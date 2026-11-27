"""The scan configuration file (cosmosproof.yml)."""

from __future__ import annotations

from datetime import date, datetime
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
    federation: bool = Field(
        True, description="Analyze Lakehouse Federation connections nobody uses (risk reading)."
    )
    list_price_discount: float = Field(
        0.0,
        ge=0,
        lt=1,
        description="Your contract discount on Databricks list prices, e.g. 0.2 for 20%.",
    )


class AccessLogs(BaseModel):
    """Azure Storage resource logs (category StorageRead) sent to a Log Analytics workspace."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(description="Log Analytics workspace ID (customer ID).")
    since: datetime = Field(description="When read logging was enabled for the account.")


class StorageConfig(BaseModel):
    """One ADLS Gen2 container and its Blob Inventory report."""

    model_config = ConfigDict(extra="forbid")

    account: str
    container: str
    inventory: str | None = Field(
        None,
        description="Path to a Blob Inventory report file (CSV or Parquet) for this container.",
    )
    list_directly: bool = Field(
        False,
        description=(
            "List the container with the Azure SDK instead of reading an inventory report "
            "(needs the `azure` extra and Storage Blob Data Reader)."
        ),
    )
    access_logs: AccessLogs | None = Field(
        None,
        description="Read events from storage resource logs: exact times, no one-day granularity.",
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


class AutoStorage(BaseModel):
    """Find the containers to list from the tables' storage paths, limited to these accounts.
    External locations are only visible to principals with privileges on them; table storage
    paths are visible with BROWSE."""

    model_config = ConfigDict(extra="forbid")

    accounts: list[str]
    exclude: list[str] = Field([], description="container@account pairs to leave out.")
    access_tracking_since: date | None = None
    access_logs: AccessLogs | None = None


class ScanConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_days: int = Field(180, ge=1, description="No read in this many days means unused.")
    window_hours: float | None = Field(
        None,
        gt=0,
        description=(
            "A window in hours ending now, instead of window_days. Needs storage read logs: "
            "last access time only has a one-day granularity."
        ),
    )
    reference_date: date | None = None
    orphan_depth: int = Field(
        2, ge=1, description="Directory depth used to group storage not owned by any table."
    )
    exclude_catalogs: list[str] = Field(
        ["samples"], description="Catalogs to ignore; `samples` holds Databricks example datasets."
    )
    databricks: DatabricksConfig | None = None
    storage: list[StorageConfig] = []
    auto_storage: AutoStorage | None = None
    publish: str | None = Field(
        None,
        description=(
            "Where each run is published for monitoring: an abfss:// URL CosmosProof owns, or a "
            "local folder. The only place CosmosProof ever writes."
        ),
    )
    rates: Rates | None = None


def load_config(path: str | Path) -> ScanConfig:
    with Path(path).open(encoding="utf-8") as fh:
        return parse_config(fh.read())


def parse_config(text: str) -> ScanConfig:
    raw = yaml.safe_load(text) or {}
    return ScanConfig.model_validate(_expand_env(raw))
