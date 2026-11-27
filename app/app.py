"""CosmosProof app (Databricks App): see the results, choose what to analyze, and know what
access is missing. Reads cosmosproof.audit and writes selection.json through a Unity Catalog
volume, with the app's own identity; no Azure credential lives here."""

from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path

import duckdb
import logic
import pandas as pd
import streamlit as st

VOLUME = os.environ.get("COSMOSPROOF_VOLUME", "")
LOCAL = os.environ.get("COSMOSPROOF_LOCAL_DIR", "")  # tests and local runs
IDENTITY = logic.Identity(
    application_id=os.environ.get("COSMOSPROOF_IDENTITY_APP_ID", ""),
    object_id=os.environ.get("COSMOSPROOF_IDENTITY_OBJECT_ID", ""),
)

st.set_page_config(page_title="CosmosProof", page_icon="🔎", layout="wide")


def _files():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient().files


def read_bytes(name: str) -> bytes | None:
    if LOCAL:
        path = Path(LOCAL) / name
        return path.read_bytes() if path.exists() else None
    try:
        return _files().download(f"{VOLUME}/{name}").contents.read()
    except Exception:
        return None


def write_text(name: str, text: str) -> None:
    if LOCAL:
        (Path(LOCAL) / name).write_text(text, encoding="utf-8")
        return
    _files().upload(f"{VOLUME}/{name}", io.BytesIO(text.encode()), overwrite=True)


@st.cache_data(ttl=300, show_spinner=False)
def load_store(source: str) -> tuple[dict, list[dict]]:
    """`source` is only the cache key, so a different store is never served from cache."""
    data = read_bytes("cosmosproof.audit")
    if not data:
        return {"run": None}, []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cosmosproof.audit"
        path.write_bytes(data)
        con = duckdb.connect(str(path), read_only=True)
        try:
            return logic.overview(con), logic.resources(con)
        finally:
            con.close()


def user_email() -> str:
    try:
        return st.context.headers.get("X-Forwarded-Email") or "unknown"
    except Exception:
        return "unknown"


def money(value, currency) -> str:
    return f"{value:,.2f} {currency or ''}".strip() if value is not None else "—"


def gigabytes(value) -> str:
    return f"{(value or 0) / 1024**3:,.2f} GB"


lang = st.sidebar.radio(
    "Idioma / Language", ["pt", "en"], format_func=lambda c: {"pt": "Português", "en": "English"}[c]
)
T = logic.TEXT[lang]
st.title(T["title"])
st.caption(T["tagline"])

data, resource_rows = load_store(LOCAL or VOLUME)
tab_overview, tab_resources, tab_connections = st.tabs(
    [T["tab_overview"], T["tab_resources"], T["tab_connections"]]
)

with tab_overview:
    if not data.get("run"):
        st.info(T["no_run"])
    else:
        k = data["kpis"]
        st.caption(f"{T['last_run']}: {data['run']['started_at']:%Y-%m-%d %H:%M} UTC")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric(
            T["open_findings"],
            k["open_findings"],
            delta=f"+{k['new_findings']}" if k["new_findings"] else None,
            delta_color="inverse",
        )
        c2.metric(T["monthly_cost"], money(k["monthly_cost"], k["currency"]))
        c3.metric(T["unused_storage"], gigabytes(k["unused_bytes"]))
        c4.metric(T["pii"], k["pii_findings"])
        c5.metric(T["risk"], k["risk_findings"])

        left, middle, right = st.columns(3)
        with left:
            st.subheader(T["by_reading"])
            if data["by_reading"]:
                st.bar_chart(pd.DataFrame(data["by_reading"]), x="reading", y="findings")
        with middle:
            st.subheader(T["by_owner"])
            owners = pd.DataFrame(data["by_owner"]).fillna({"monthly_cost": 0})
            if not owners.empty:
                st.bar_chart(owners, x="owner", y="monthly_cost", horizontal=True)
        with right:
            st.subheader(T["trend"])
            trend = pd.DataFrame(data["trend"])
            if not trend.empty:
                st.line_chart(trend, x="started_at", y="open_findings")

        st.subheader(T["findings"])
        findings = pd.DataFrame(data["findings"])
        f1, f2 = st.columns(2)
        readings = f1.multiselect(T["filter_reading"], sorted(findings["reading"].unique()))
        names = f2.multiselect(
            T["filter_resource"], sorted(findings["resource_name"].dropna().unique())
        )
        if readings:
            findings = findings[findings["reading"].isin(readings)]
        if names:
            findings = findings[findings["resource_name"].isin(names)]
        for _, f in findings.iterrows():
            cost = (
                f" · {money(f['monthly_cost'], f['currency'])}"
                if pd.notna(f["monthly_cost"])
                else ""
            )
            title = (
                f"**{f['asset']}** · {f['kind']} · {f['confidence']} · {f['owner'] or '—'}{cost}"
            )
            with st.expander(title):
                st.markdown(f"**{T['recommendation']}:** {f['recommendation']}")
                st.markdown(f"**{T['evidence']}:**")
                for e in logic.parse_json(f["evidence"]):
                    when = f" ({e['observed_at'][:10]})" if e.get("observed_at") else ""
                    st.markdown(f"- {e['source']}: {e['signal']}{when}")
                notes = logic.parse_json(f["coverage_notes"])
                if notes:
                    st.markdown(f"**{T['not_seen']}:**")
                    for n in notes:
                        st.markdown(f"- {n}")
                st.code(f"{T['proof']}: {f['proof_hash']}", language=None)

with tab_resources:
    st.write(T["resources_help"])
    if resource_rows:
        frame = pd.DataFrame(resource_rows)
        if st.button(T["leave_out_nonprod"]):
            choices = logic.leave_out_nonproduction(resource_rows)
            frame["selected"] = frame["resource_id"].map(choices)
            st.session_state["pending"] = choices
        frame["kind"] = frame["kind"].map({"workspace": T["workspace"], "storage": T["storage"]})
        edited = st.data_editor(
            frame[
                [
                    "selected",
                    "name",
                    "kind",
                    "environment",
                    "resource_group",
                    "managed_by",
                    "resource_id",
                ]
            ],
            column_config={
                "selected": st.column_config.CheckboxColumn(T["analyze"]),
                "name": T["name"],
                "kind": T["kind"],
                "environment": T["environment"],
                "resource_group": T["resource_group"],
                "managed_by": T["managed_by"],
                "resource_id": None,
            },
            disabled=["name", "kind", "environment", "resource_group", "managed_by"],
            hide_index=True,
            width="stretch",
            key="selection_editor",
        )
        if st.button(T["save"], type="primary"):
            current = json.loads(read_bytes("selection.json") or b"{}")
            choices = dict(zip(edited["resource_id"], edited["selected"].astype(bool), strict=True))
            write_text(
                "selection.json",
                json.dumps(logic.apply_selection(current, choices, user_email()), indent=2),
            )
            st.success(T["saved"])

with tab_connections:
    st.write(T["connections_help"])
    health = data.get("health") or []
    if health:
        labels = {"ok": T["ready"], "error": T["missing"], None: T["not_scanned"]}
        table = pd.DataFrame(health)
        table = table[table["selected"]]
        table["status"] = table["last_scan_status"].map(lambda s: labels.get(s, s))
        st.dataframe(
            table[["name", "kind", "environment", "status", "last_scan_error"]],
            hide_index=True,
            width="stretch",
        )
        st.download_button(
            T["download_script"],
            logic.access_script(health, resource_rows, IDENTITY),
            file_name="cosmosproof-access.sh",
        )
