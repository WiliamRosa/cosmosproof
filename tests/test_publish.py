import json

from cosmosproof.demo import demo_report
from cosmosproof.publish import LocalTarget, previous_report, publish, run_id


def test_publish_marks_new_ongoing_and_resolved(tmp_path):
    target = LocalTarget(tmp_path)
    first = demo_report()
    counts = publish(first, target)
    assert counts == {"new": len(first.findings), "ongoing": 0, "resolved": 0}

    # Second run a moment later where the first finding is gone.
    second = first.model_copy(
        update={
            "findings": first.findings[1:],
            "generated_at": first.generated_at.replace(microsecond=0).replace(
                second=(first.generated_at.second + 1) % 60
            ),
        }
    )
    if run_id(second) == run_id(first):
        second = second.model_copy(update={"generated_at": second.generated_at.replace(year=2027)})
    counts = publish(second, target)
    assert counts == {"new": 0, "ongoing": len(first.findings) - 1, "resolved": 1}

    rows = [
        json.loads(line)
        for line in (tmp_path / f"findings/{run_id(second)}.jsonl").read_text().splitlines()
    ]
    resolved = [r for r in rows if r["status"] == "resolved"]
    assert [r["id"] for r in resolved] == [first.findings[0].id]
    assert resolved[0]["monthly_cost"] is None
    assert all(r["proof_hash"].startswith("sha256:") for r in rows)
    assert previous_report(target).generated_at == second.generated_at
    summary = json.loads((tmp_path / f"summaries/{run_id(second)}.json").read_text())
    assert summary["open_findings"] == len(first.findings) - 1
    assert summary["resolved_findings"] == 1 and summary["currency"] == "USD"


def test_cli_publish_and_env_config(tmp_path, monkeypatch, duck):
    # The CLI path is covered with a local folder; the env config path with a minimal file.
    from typer.testing import CliRunner

    from cosmosproof.cli import app

    monkeypatch.setenv("COSMOSPROOF_CONFIG", "window_days: 30\n")
    result = CliRunner().invoke(app, ["scan", "--publish", str(tmp_path)])
    # No databricks section: the scan must refuse with a clear message, not crash on publish.
    assert result.exit_code != 0
    assert result.exit_code == 2 and "databricks" in result.output


def test_azure_auth_turns_into_an_access_token(monkeypatch):
    import azure.identity
    from cosmos_semantic.connectors import DataSourceConfig

    from cosmosproof.scan import AZURE_DATABRICKS_RESOURCE, _with_azure_token

    asked = []

    class FakeCredential:
        def __init__(self, **kwargs):
            pass

        def get_token(self, scope):
            asked.append(scope)
            return type("T", (), {"token": "entra-token"})()

    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", FakeCredential)
    source = DataSourceConfig(
        type="databricks", options={"server_hostname": "h", "http_path": "/p", "auth": "azure"}
    )
    out = _with_azure_token(source)
    assert out.options == {"server_hostname": "h", "http_path": "/p", "access_token": "entra-token"}
    assert asked == [f"{AZURE_DATABRICKS_RESOURCE}/.default"]
    plain = DataSourceConfig(type="databricks", options={"access_token": "x"})
    assert _with_azure_token(plain) is plain
