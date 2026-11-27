"""Builds a fictional audit store and captures the app at 1280x720 for the Marketplace listing
and the website. Nothing here comes from a real tenant: owners, names and numbers are the
fictional bank of `cosmosproof demo`.

    uv run --with playwright python deploy/azure/marketplace/capture.py

Needs Google Chrome installed. Writes screenshots/0N-*.png next to this file.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent / "screenshots"
PORT = 8599
SUB = "/subscriptions/3f2b0c1a-0000-4000-8000-banco0000001"


def build_store(folder: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from cosmosproof.demo import demo_report
    from cosmosproof.discovery import Resource
    from cosmosproof.store import FILE_NAME, AuditStore

    def ws(name, rg, env):
        return Resource(f"{SUB}/resourceGroups/{rg}/providers/Microsoft.Databricks/workspaces/{name}",
                        "workspace", name, SUB.rsplit("/", 1)[1], rg, "brazilsouth",
                        environment=env, environment_source="name", status="ready")  # fmt: skip

    def sa(name, rg, env, source="tag", managed=None):
        return Resource(f"{SUB}/resourceGroups/{rg}/providers/Microsoft.Storage/storageAccounts/{name}",
                        "storage", name, SUB.rsplit("/", 1)[1], rg, "brazilsouth",
                        environment=env, environment_source=source, managed_by=managed)  # fmt: skip

    varejo = ws("dbx-varejo-prd", "rg-dados-varejo-prd", "prod")
    credito = ws("dbx-credito-prd", "rg-dados-credito-prd", "prod")
    poc = ws("dbx-poc-open-finance", "rg-inovacao-poc", "poc")
    resources = [
        varejo,
        credito,
        poc,
        sa("lakevarejoprd", "rg-dados-varejo-prd", "prod"),
        sa("lakecreditoprd", "rg-dados-credito-prd", "prod"),
        sa("lakesandboxdev", "rg-analytics-dev", "dev"),
        sa("dbstoragepocof", "rg-inovacao-poc-managed", "poc", "workspace", "dbx-poc-open-finance"),
    ]
    chosen = {r.id: r.environment == "prod" for r in resources}
    findings = demo_report().findings
    split = {varejo.id: findings[:3], credito.id: findings[3:]}
    with AuditStore(folder / FILE_NAME) as store:
        store.upsert_resources(resources, chosen)
        day1 = datetime(2026, 11, 26, 6, tzinfo=UTC)
        first = [(rid, f) for rid, fs in split.items() for f in fs]
        store.record_run("20261126T060000000Z", day1, "0.1.0", 180, first, 2, 0)
        for rid in split:
            store.record_resource_scan("20261126T060000000Z", rid, status="ok")
        # Next day: one finding was handled.
        second = first[1:]
        store.record_run(
            "20261127T060000000Z", day1 + timedelta(days=1), "0.1.0", 180, second, 2, 0,
            judged=set(split),
        )  # fmt: skip
        store.record_resource_scan("20261127T060000000Z", varejo.id, status="ok")
        store.record_resource_scan(
            "20261127T060000000Z", credito.id, status="error",
            error="The identity has no CAN USE on a SQL warehouse in this workspace.",
        )  # fmt: skip


def capture(base: str) -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)

        def shot(name: str) -> None:
            # Keep the pointer off the sidebar (its hover button shows an icon-font ligature).
            page.mouse.move(800, 450)
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(1500)
            page.screenshot(path=str(OUT / name))
            print("wrote", OUT / name)

        def tab(label: str) -> None:
            page.get_by_role("tab", name=label).click()

        page.goto(f"{base}/?embed=false")
        page.wait_for_selector("text=Achados abertos", timeout=60000)
        page.get_by_text("English").click()
        page.wait_for_selector("text=Open findings")
        shot("01-overview.png")

        page.mouse.wheel(0, 700)
        page.wait_for_timeout(800)
        page.locator("details.cp-card").first.locator("summary").click()
        shot("02-findings-evidence.png")

        page.get_by_text("Dark mode").click()
        page.mouse.move(800, 450)
        page.wait_for_timeout(800)
        page.mouse.wheel(0, -3000)
        shot("03-overview-dark.png")
        page.get_by_text("Dark mode").click()

        tab("Resources")
        shot("04-resources.png")
        tab("Connections")
        shot("05-connections.png")
        browser.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        build_store(folder)
        env = {**os.environ, "COSMOSPROOF_LOCAL_DIR": str(folder)}
        server = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", str(ROOT / "app" / "app.py"),
             "--server.headless", "true", "--server.port", str(PORT),
             "--browser.gatherUsageStats", "false", "--client.toolbarMode", "viewer"],
            cwd=ROOT / "app", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        try:
            for _ in range(60):
                try:
                    urllib.request.urlopen(f"http://localhost:{PORT}/_stcore/health", timeout=2)
                    break
                except Exception:
                    time.sleep(1)
            capture(f"http://localhost:{PORT}")
        finally:
            server.terminate()


if __name__ == "__main__":
    main()
