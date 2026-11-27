import json
import sys
from pathlib import Path

import pytest

APP = Path(__file__).parent.parent / "app"
sys.path.insert(0, str(APP))

import logic  # noqa: E402

from cosmosproof.audit import merge_selection, parse_audit_config, run_audit  # noqa: E402
from cosmosproof.demo import demo_report  # noqa: E402
from cosmosproof.discovery import Resource  # noqa: E402

WS = Resource(
    "/ws/prd", "workspace", "wkp-prd", "s", "rg", "l", environment="prod",
    host="adb-1.1.azuredatabricks.net", status="ready",
    warehouses=[{"id": "abc123", "enable_serverless_compute": True}],
    locations=["abfss://lake@acct1.dfs.core.windows.net/"],
)  # fmt: skip
DEV = Resource("/ws/dev", "workspace", "wkp-dev", "s", "rg", "l", environment="dev", status="ready")
SA = Resource("/sa/acct1", "storage", "acct1", "s", "rg", "l", environment="prod")


@pytest.fixture
def audit_dir(tmp_path, monkeypatch):
    import cosmosproof.audit as audit

    monkeypatch.setattr(audit, "run_scan", lambda cfg: demo_report())
    config = parse_audit_config(f"location: {tmp_path.as_posix()}\n")
    run_audit(config, discovered=([WS, DEV, SA], merge_selection([WS, DEV, SA], {})))
    return tmp_path


def test_selection_records_who_changed_what():
    current = {
        "resources": {
            "/ws/prd": {"selected": True, "by": "suggestion"},
            "/ws/x": {"selected": True, "by": "ana"},
        }
    }
    out = logic.apply_selection(current, {"/ws/prd": True, "/ws/x": True}, "maria@bank")[
        "resources"
    ]
    assert out["/ws/prd"]["by"] == "maria@bank"  # confirming a suggestion makes it a choice
    assert out["/ws/x"] == {"selected": True, "by": "ana"}  # unchanged choice stays


def test_leave_out_nonproduction():
    rows = [
        {"resource_id": "a", "selected": True, "environment": "prod"},
        {"resource_id": "b", "selected": True, "environment": "poc"},
        {"resource_id": "c", "selected": False, "environment": "unknown"},
    ]
    assert logic.leave_out_nonproduction(rows) == {"a": True, "b": False, "c": False}


def test_access_script_groups_by_administrator():
    health = [
        {
            "resource_id": "/sa/acct1",
            "selected": True,
            "last_scan_status": None,
            "discovery_status": "discovered",
        },
        {
            "resource_id": "/ws/prd",
            "selected": True,
            "last_scan_status": "error",
            "discovery_status": "ready",
        },
        {
            "resource_id": "/ws/ok",
            "selected": True,
            "last_scan_status": "ok",
            "discovery_status": "ready",
        },
    ]
    rows = [
        {"resource_id": "/sa/acct1", "kind": "storage", "name": "acct1"},
        {"resource_id": "/ws/prd", "kind": "workspace", "name": "wkp-prd"},
        {"resource_id": "/ws/ok", "kind": "workspace", "name": "wkp-ok"},
    ]
    script = logic.access_script(health, rows, logic.Identity("app-1", "obj-1"))
    assert "## Azure administrator" in script and "--scope /sa/acct1" in script
    assert "## Databricks workspace administrator" in script and "wkp-prd" in script
    assert "wkp-ok" not in script


def _app(local_dir, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("COSMOSPROOF_LOCAL_DIR", str(local_dir))
    monkeypatch.chdir(APP)
    return AppTest.from_file(str(APP / "app.py"), default_timeout=30)


def test_app_renders_results(audit_dir, monkeypatch):
    at = _app(audit_dir, monkeypatch).run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Achados abertos" in labels and "PII parado" in labels
    assert int(at.metric[0].value) == len(demo_report().findings)
    cards = "".join(m.value for m in at.markdown).count('class="cp-card"')
    assert cards == len(demo_report().findings)


def test_app_dark_mode_and_pagination(audit_dir, monkeypatch):
    at = _app(audit_dir, monkeypatch).run()
    at.toggle(key="dark_mode").set_value(True).run()
    assert not at.exception
    css = "".join(m.value for m in at.markdown)
    assert "#0f1419" in css  # dark background
    at.selectbox(key="findings_size").set_value(10).run()
    assert "página 1 de 1" in "".join(m.value for m in at.markdown)


def test_app_resource_toggles_and_leave_out(audit_dir, monkeypatch):
    at = _app(audit_dir, monkeypatch).run()
    toggles = [t for t in at.toggle if str(t.key).startswith("sel::")]
    assert {t.key for t in toggles} == {"sel::/ws/prd", "sel::/ws/dev", "sel::/sa/acct1"}
    at.toggle(key="sel::/ws/dev").set_value(True).run()
    assert at.session_state["choices"]["/ws/dev"] is True
    next(b for b in at.button if b.label.startswith("Deixar de fora")).click().run()
    assert at.session_state["choices"]["/ws/dev"] is False
    assert at.session_state["choices"]["/ws/prd"] is True


def test_app_saves_the_selection(audit_dir, monkeypatch):
    at = _app(audit_dir, monkeypatch).run()
    save = next(b for b in at.button if b.label == "Salvar seleção")
    save.click().run()
    assert not at.exception
    saved = json.loads((audit_dir / "selection.json").read_text())
    assert saved["resources"]["/ws/prd"]["by"] == "unknown"  # no proxy header in tests
    assert saved["resources"]["/ws/dev"]["selected"] is False


def test_app_without_any_run(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch).run()
    assert not at.exception
    assert any("Ainda não há nenhuma execução" in i.value for i in at.info)


def test_ui_escapes_and_colors():
    import ui

    card = ui.finding_card(
        {"asset": "<script>x</script>", "reading": "cost", "confidence": "high",
         "owner": "a@b", "resource_group": "rg-1", "proof_hash": "sha256:1"},
        logic.TEXT["en"], "light", [{"source": "s", "signal": "<b>"}], [],
    )  # fmt: skip
    assert "<script>" not in card and "&lt;script&gt;" in card and "&lt;b&gt;" in card
    assert ui.color_for("rg-1") == ui.color_for("RG-1")
    assert ui.page(list(range(23)), 3, 10) == ([20, 21, 22], 3)
    assert ui.page([], 5, 10) == ([], 1)


def test_badges_keep_black_text_in_both_themes():
    import ui

    for theme in ("light", "dark"):
        assert ".stApp span.cp-badge { color: #1f2328 !important; }" in ui.css(theme)


def test_page_arrows(tmp_path, monkeypatch):
    import cosmosproof.audit as audit
    from cosmosproof.demo import demo_report

    report = demo_report()
    many = []
    for i in range(3):  # 15 findings with distinct ids: two pages of 10
        many += [f.model_copy(update={"id": f"{f.id}{i}"}) for f in report.findings]
    monkeypatch.setattr(audit, "run_scan", lambda cfg: report.model_copy(update={"findings": many}))
    config = parse_audit_config(f"location: {tmp_path.as_posix()}\n")
    run_audit(config, discovered=([WS, SA], merge_selection([WS, SA], {})))

    at = _app(tmp_path, monkeypatch).run()
    assert at.button(key="findings_prev").disabled and at.button(key="findings_first").disabled
    at.button(key="findings_next").click().run()
    text = "".join(m.value for m in at.markdown)
    assert "Página 2 de 2" in text
    assert text.count('class="cp-card"') == 5
    assert at.button(key="findings_last").disabled
    at.button(key="findings_first").click().run()
    assert "Página 1 de 2" in "".join(m.value for m in at.markdown)
