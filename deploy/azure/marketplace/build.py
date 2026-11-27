"""Builds the Managed Application package for Partner Center.

    python deploy/azure/marketplace/build.py

Compiles main.bicep to mainTemplate.json (needs the Azure CLI with Bicep) and zips it with
createUiDefinition.json at the root of cosmosproof-managed-app.zip, the file to upload in the
plan's technical configuration.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

HERE = Path(__file__).parent


def main() -> None:
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
    package = HERE / "cosmosproof-managed-app.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(HERE / "mainTemplate.json", "mainTemplate.json")
        z.write(HERE / "createUiDefinition.json", "createUiDefinition.json")
    print(f"package: {package}")


if __name__ == "__main__":
    main()
