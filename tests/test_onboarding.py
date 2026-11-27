import json

from typer.testing import CliRunner

from cosmosproof.cli import app
from cosmosproof.inventory import parse_time
from cosmosproof.onboarding import INVENTORY_FIELDS, StorageAccount, inventory_policy

runner = CliRunner()


def test_inventory_policy_shape():
    policy = inventory_policy("inv", "daily")
    rule = policy["rules"][0]
    assert policy["enabled"] is True
    assert rule["destination"] == "inv"
    assert rule["definition"]["objectType"] == "blob"
    assert rule["definition"]["format"] == "csv"
    assert rule["definition"]["schedule"] == "daily"
    assert "LastAccessTime" in rule["definition"]["schemaFields"]
    assert INVENTORY_FIELDS[0] == "Name"


def test_storage_account_parse():
    assert StorageAccount.parse("rg-data/lake01") == StorageAccount("rg-data", "lake01")


def test_grants_command():
    result = runner.invoke(
        app,
        [
            "grants",
            "--application-id",
            "app-123",
            "--object-id",
            "obj-456",
            "--subscription",
            "sub-789",
            "--storage",
            "rg-data/lake01",
            "--catalog",
            "main",
        ],
    )
    assert result.exit_code == 0, result.output
    out = result.output
    assert "GRANT SELECT ON SCHEMA system.access TO `app-123`;" in out
    assert "GRANT SELECT ON SCHEMA system.billing TO `app-123`;" in out
    assert "GRANT BROWSE ON CATALOG `main` TO `app-123`;" in out
    assert (
        "--scope /subscriptions/sub-789/resourceGroups/rg-data/providers/"
        "Microsoft.Storage/storageAccounts/lake01" in out
    )
    assert "--enable-last-access-tracking true" in out
    # Only read roles: CosmosProof never needs to write.
    assert "Contributor" not in out and "Owner" not in out
    policy = json.loads(out[out.index("{") :])
    assert policy["rules"][0]["destination"] == "cosmosproof-inventory"


def test_grants_rejects_bad_storage():
    result = runner.invoke(
        app,
        [
            "grants",
            "--application-id",
            "a",
            "--object-id",
            "o",
            "--subscription",
            "s",
            "--storage",
            "nope",
        ],
    )
    assert result.exit_code != 0


def test_parquet_millisecond_timestamps():
    assert parse_time(1_767_225_600_000).isoformat() == "2026-01-01T00:00:00+00:00"


def test_example_config_loads(monkeypatch):
    from pathlib import Path

    from cosmosproof.config import load_config

    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/x")
    config = load_config(Path(__file__).parent.parent / "examples" / "cosmosproof.yml")
    assert config.databricks.producers is True
    assert config.storage[0].account == "mydatalake"
