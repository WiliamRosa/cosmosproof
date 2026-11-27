"""Partner Center checks that rejected the Cosmos Semantic package once, kept as tests."""

import json
import re
from pathlib import Path

HERE = Path(__file__).parent.parent / "deploy" / "azure" / "marketplace"


def _ui():
    return json.loads((HERE / "createUiDefinition.json").read_text(encoding="utf-8"))


def _elements(ui):
    for step in ui["parameters"]["steps"]:
        yield from step["elements"]


def test_every_textbox_has_a_working_regex():
    # arm-ttk "Textboxes Are Well Formed": every TextBox, required or not, needs a regex.
    for element in _elements(_ui()):
        if element["type"] != "Microsoft.Common.TextBox":
            continue
        validations = element["constraints"]["validations"]
        regex = next(v["regex"] for v in validations if v.get("regex"))
        re.compile(regex)
        assert all(v.get("message") for v in validations), element["name"]


def test_textbox_defaults_satisfy_their_regex():
    for element in _elements(_ui()):
        if element["type"] == "Microsoft.Common.TextBox" and "defaultValue" in element:
            regex = element["constraints"]["validations"][0]["regex"]
            assert re.fullmatch(regex, element["defaultValue"]), element["name"]


def test_ui_outputs_match_template_parameters():
    template = json.loads((HERE / "mainTemplate.json").read_text(encoding="utf-8"))
    params = template["parameters"]
    outputs = set(_ui()["parameters"]["outputs"])
    assert outputs <= set(params), outputs - set(params)
    required = {name for name, p in params.items() if "defaultValue" not in p}
    assert required <= outputs, required - outputs


def test_template_attribution_and_read_only_roles():
    template = (HERE / "main.bicep").read_text(encoding="utf-8")
    assert "pid-${partnerCenterPid}-partnercenter" in template
    # The only role the template grants is a data writer on its own reports container.
    assert template.count("Microsoft.Authorization/roleAssignments") == 1
    assert "scope: reportsContainerResource" in template


def test_packaged_template_carries_the_attribution_pid():
    import importlib.util

    import pytest

    spec = importlib.util.spec_from_file_location("build", HERE / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    template = (HERE / "mainTemplate.json").read_text(encoding="utf-8")
    pid = "0F8C1A2B-1111-4222-8333-944455556666"
    packaged = json.loads(build.packaged_template(template, pid))
    assert packaged["parameters"]["partnerCenterPid"]["defaultValue"] == pid.lower()
    # Partner Center needs the literal deployment name, with no condition.
    (attribution,) = [r for r in packaged["resources"] if r["type"] == "Microsoft.Resources/deployments"]
    assert attribution["name"] == f"pid-{pid.lower()}-partnercenter"
    assert "condition" not in attribution
    # The committed template stays without attribution.
    assert json.loads(template)["parameters"]["partnerCenterPid"]["defaultValue"] == ""
    assert build.packaged_template(template, None) == template
    with pytest.raises(SystemExit):
        build.packaged_template(template, "not-a-guid")
