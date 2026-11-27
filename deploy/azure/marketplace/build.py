"""Builds the Managed Application package for Partner Center.

    python deploy/azure/marketplace/build.py --pid <customer usage attribution GUID>

Compiles main.bicep to mainTemplate.json (needs the Azure CLI with Bicep) and zips it with
createUiDefinition.json at the root of cosmosproof-managed-app.zip, the file to upload in the
plan's technical configuration.

The wizard does not pass `partnerCenterPid`, so a Marketplace deployment only reports usage
attribution when the GUID is the parameter's default. `--pid` sets that default in the packaged
template only; the committed mainTemplate.json keeps it empty.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def packaged_template(template: str, pid: str | None) -> str:
    """The template as packaged: with the attribution GUID as the default when one is given."""
    if not pid:
        return template
    if not GUID.match(pid):
        raise SystemExit(f"--pid must be a GUID, got {pid!r}")
    pid = pid.lower()
    data = json.loads(template)
    data["parameters"]["partnerCenterPid"]["defaultValue"] = pid
    # Partner Center only recognizes the attribution deployment by its literal name: with an
    # expression it reports "deployments used for purposes other than customer usage attribution"
    # and refuses the package.
    for resource in data["resources"]:
        if resource["type"] == "Microsoft.Resources/deployments":
            resource["name"] = f"pid-{pid}-partnercenter"
            resource.pop("condition", None)
    return json.dumps(data, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pid", help="customer usage attribution GUID from Partner Center")
    args = parser.parse_args()

    az = shutil.which("az") or shutil.which("az.cmd")
    if not az:
        raise SystemExit("the Azure CLI (az) is needed to compile main.bicep")
    subprocess.run(
        [
            az,
            "bicep",
            "build",
            "--file",
            str(HERE / "main.bicep"),
            "--outfile",
            str(HERE / "mainTemplate.json"),
        ],
        check=True,
    )
    template = packaged_template((HERE / "mainTemplate.json").read_text(encoding="utf-8"), args.pid)
    package = HERE / "cosmosproof-managed-app.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mainTemplate.json", template)
        z.write(HERE / "createUiDefinition.json", "createUiDefinition.json")
    note = f"attribution {args.pid.lower()}" if args.pid else "no attribution"
    print(f"package: {package} ({note})")


if __name__ == "__main__":
    main()
