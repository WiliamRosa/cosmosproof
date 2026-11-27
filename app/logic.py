"""What the CosmosProof app does, without any UI: read the audit store, change the selection,
and write the access script for administrators. Kept apart so it can be tested headless."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import duckdb

NON_PRODUCTION = {"dev", "poc", "test"}

TEXT = {
    "pt": {
        "title": "CosmosProof",
        "tagline": "Lakehouse FinOps: o que no seu lake custa dinheiro, gera risco ou guarda PII sem uso, com a prova de cada achado.",
        "tab_overview": "Visão geral",
        "tab_resources": "Recursos",
        "tab_connections": "Conexões",
        "open_findings": "Achados abertos",
        "monthly_cost": "Custo mensal estimado",
        "unused_storage": "Storage sem uso",
        "pii": "PII parado",
        "risk": "Riscos",
        "new": "Novos desde a última execução",
        "by_reading": "Achados por leitura",
        "by_owner": "Custo mensal por dono",
        "trend": "Achados abertos por execução",
        "findings": "Achados",
        "filter_reading": "Leitura",
        "filter_resource": "Recurso",
        "evidence": "Evidência",
        "not_seen": "O que não pôde ser visto",
        "recommendation": "Recomendação",
        "proof": "Prova",
        "no_run": "Ainda não há nenhuma execução. A primeira análise acontece no horário agendado.",
        "resources_help": "Escolha o que o CosmosProof deve analisar. Recursos de desenvolvimento e POC começam desmarcados.",
        "leave_out_nonprod": "Deixar de fora tudo que é desenvolvimento, teste ou POC",
        "analyze": "Analisar",
        "name": "Nome",
        "kind": "Tipo",
        "environment": "Ambiente",
        "resource_group": "Resource group",
        "managed_by": "Gerenciado por",
        "save": "Salvar seleção",
        "saved": "Seleção salva. Ela vale a partir da próxima análise.",
        "connections_help": "Situação de cada recurso escolhido na última análise. Para o que falta, baixe o script e peça para os administradores executarem.",
        "status": "Situação",
        "ready": "Pronto",
        "missing": "Falta acesso",
        "not_scanned": "Ainda não analisado",
        "download_script": "Baixar script de acesso",
        "language": "Idioma",
        "last_run": "Última análise",
        "workspace": "Workspace Databricks",
        "storage": "Conta ADLS",
        "dark_mode": "Modo escuro",
        "reading_cost": "Custo",
        "reading_risk": "Risco",
        "reading_compliance": "PII",
        "owner": "Dono",
        "legend": "Cores por resource group",
        "per_page": "Por página",
        "page": "Página",
        "showing": "Mostrando {n} de {total} · página {page} de {pages}",
        "selected_count": "{n} de {total} selecionados",
        "suggested_by": "sugerido por",
        "detail": "Detalhe",
        "env_prod": "Produção",
        "env_dev": "Desenvolvimento",
        "env_test": "Teste",
        "env_poc": "POC",
        "env_unknown": "Não identificado",
    },
    "en": {
        "title": "CosmosProof",
        "tagline": "Lakehouse FinOps: what in your lake costs money, creates risk or holds PII without being used, with the proof behind each finding.",
        "tab_overview": "Overview",
        "tab_resources": "Resources",
        "tab_connections": "Connections",
        "open_findings": "Open findings",
        "monthly_cost": "Estimated monthly cost",
        "unused_storage": "Unused storage",
        "pii": "PII at rest",
        "risk": "Risks",
        "new": "New since the last run",
        "by_reading": "Findings by reading",
        "by_owner": "Monthly cost by owner",
        "trend": "Open findings per run",
        "findings": "Findings",
        "filter_reading": "Reading",
        "filter_resource": "Resource",
        "evidence": "Evidence",
        "not_seen": "What could not be seen",
        "recommendation": "Recommendation",
        "proof": "Proof",
        "no_run": "No run yet. The first analysis happens at the scheduled time.",
        "resources_help": "Choose what CosmosProof analyzes. Development and POC resources start unselected.",
        "leave_out_nonprod": "Leave out everything marked development, test or POC",
        "analyze": "Analyze",
        "name": "Name",
        "kind": "Type",
        "environment": "Environment",
        "resource_group": "Resource group",
        "managed_by": "Managed by",
        "save": "Save selection",
        "saved": "Selection saved. It applies from the next analysis.",
        "connections_help": "Status of each chosen resource in the last analysis. For what is missing, download the script and ask the administrators to run it.",
        "status": "Status",
        "ready": "Ready",
        "missing": "Missing access",
        "not_scanned": "Not analyzed yet",
        "download_script": "Download access script",
        "language": "Language",
        "last_run": "Last analysis",
        "workspace": "Databricks workspace",
        "storage": "ADLS account",
        "dark_mode": "Dark mode",
        "reading_cost": "Cost",
        "reading_risk": "Risk",
        "reading_compliance": "PII",
        "owner": "Owner",
        "legend": "Colors by resource group",
        "per_page": "Per page",
        "page": "Page",
        "showing": "Showing {n} of {total} · page {page} of {pages}",
        "selected_count": "{n} of {total} selected",
        "suggested_by": "suggested by",
        "detail": "Detail",
        "env_prod": "Production",
        "env_dev": "Development",
        "env_test": "Test",
        "env_poc": "POC",
        "env_unknown": "Not identified",
    },
}


@dataclass
class Identity:
    """CosmosProof's managed identity, as the Marketplace deployment output it."""

    application_id: str = ""
    object_id: str = ""


def query(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


def overview(con: duckdb.DuckDBPyConnection) -> dict:
    runs = query(con, "SELECT * FROM v_latest_run")
    if not runs:
        return {"run": None}
    return {
        "run": runs[0],
        "kpis": query(con, "SELECT * FROM v_kpis")[0],
        "by_reading": query(
            con,
            "SELECT reading, COUNT(*) AS findings FROM v_open_findings GROUP BY 1 ORDER BY 2 DESC",
        ),
        "by_owner": query(con, "SELECT owner, monthly_cost, findings FROM v_cost_by_owner"),
        "trend": query(con, "SELECT started_at, open_findings FROM v_trend"),
        "findings": query(
            con,
            "SELECT reading, kind, asset, owner, confidence, status, monthly_cost, currency, "
            "size_bytes, resource_name, resource_group, environment, recommendation, evidence, coverage_notes, "
            "proof_hash FROM v_open_findings ORDER BY monthly_cost DESC NULLS LAST, size_bytes DESC",
        ),
        "health": query(con, "SELECT * FROM v_resource_health"),
    }


def resources(con: duckdb.DuckDBPyConnection) -> list[dict]:
    return query(
        con,
        "SELECT resource_id, kind, name, environment, environment_source, resource_group, "
        "subscription, managed_by, selected FROM dim_resource ORDER BY kind DESC, name",
    )


def apply_selection(current: dict, choices: dict[str, bool], user: str) -> dict:
    """Records each changed choice as made by this person; untouched entries stay as they were."""
    chosen = dict(current.get("resources", {}))
    now = datetime.now(UTC).isoformat(timespec="seconds")
    for resource_id, selected in choices.items():
        previous = chosen.get(resource_id, {})
        if previous.get("selected") != selected or previous.get("by") == "suggestion":
            chosen[resource_id] = {"selected": selected, "by": user, "at": now}
    return {**current, "resources": chosen}


def leave_out_nonproduction(rows: list[dict]) -> dict[str, bool]:
    return {
        r["resource_id"]: bool(r["selected"]) and r["environment"] not in NON_PRODUCTION
        for r in rows
    }


def access_script(health: list[dict], all_resources: list[dict], identity: Identity) -> str:
    """One script for the administrators, for exactly the chosen resources that are not ready,
    grouped by who must run each part."""
    by_id = {r["resource_id"]: r for r in all_resources}
    missing = [
        h
        for h in health
        if h["selected"]
        and (h["last_scan_status"] in (None, "error") or h["discovery_status"] == "error")
    ]
    app = identity.application_id or "<application-id>"
    obj = identity.object_id or "<object-id>"
    azure, databricks = [], []
    for h in missing:
        r = by_id.get(h["resource_id"], {})
        if r.get("kind") == "storage":
            azure.append(
                f"az role assignment create --assignee-object-id {obj} "
                f'--assignee-principal-type ServicePrincipal --role "Storage Blob Data Reader" '
                f"--scope {h['resource_id']}"
            )
        elif r.get("kind") == "workspace":
            databricks += [
                f"-- Workspace {r['name']}: add service principal {app} with the "
                "'Databricks SQL access' entitlement and CAN USE on one SQL warehouse, then:",
                f"-- GRANT BROWSE ON CATALOG <each catalog to analyze> TO `{app}`;",
            ]
    lines = ["# CosmosProof access script. Review every line before running it.", ""]
    if azure:
        lines += ["## Azure administrator (Azure CLI)", *azure, ""]
    if databricks:
        lines += ["## Databricks workspace administrator", *databricks, ""]
    if not azure and not databricks:
        lines.append("# Nothing is missing.")
    return "\n".join(lines) + "\n"


def parse_json(text: str | None) -> list:
    try:
        return json.loads(text) if text else []
    except (TypeError, ValueError):
        return []
