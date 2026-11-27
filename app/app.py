"""CosmosProof app (Databricks App): see the results, choose what to analyze, and know what
access is missing. Reads cosmosproof.audit and writes selection.json through a Unity Catalog
volume, with the app's own identity; no Azure credential lives here."""

from __future__ import annotations

import html
import io
import json
import os
import tempfile
from pathlib import Path

import altair as alt
import duckdb
import logic
import pandas as pd
import streamlit as st
import ui

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


def chart(frame: pd.DataFrame, kind: str, x: str, y: str, theme: str, horizontal=False):
    t = ui.THEMES[theme]
    if kind == "line":
        base = alt.Chart(frame).mark_line(point=True, color=ui.CHART_PALETTE[0], strokeWidth=3)
        enc = base.encode(x=alt.X(x, title=None), y=alt.Y(y, title=None))
    else:
        base = alt.Chart(frame).mark_bar(cornerRadius=6)
        color = alt.Color(x, legend=None, scale=alt.Scale(range=ui.CHART_PALETTE))
        if horizontal:
            enc = base.encode(
                y=alt.Y(x, sort="-x", title=None), x=alt.X(y, title=None), color=color
            )
        else:
            enc = base.encode(
                x=alt.X(x, sort="-y", title=None), y=alt.Y(y, title=None), color=color
            )
    return (
        enc.properties(height=260)
        .configure(background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor=t["muted"],
            titleColor=t["muted"],
            gridColor=t["border"],
            domainColor=t["border"],
        )
    )


def pager(key: str, total: int, labels: dict, sizes=(10, 25, 50)) -> tuple[int, int]:
    left, right = st.columns(2)
    size = left.selectbox(labels["per_page"], sizes, key=f"{key}_size")
    pages = max(1, -(-total // size))
    number = right.number_input(
        f"{labels['page']} (1–{pages})", min_value=1, max_value=pages, value=1, key=f"{key}_page"
    )
    return int(number), int(size)


# --- sidebar and theme ---------------------------------------------------------------------

lang = st.sidebar.radio(
    "Idioma / Language", ["pt", "en"], format_func=lambda c: {"pt": "Português", "en": "English"}[c]
)
T = logic.TEXT[lang]
dark = st.sidebar.toggle(T["dark_mode"], key="dark_mode")
theme = "dark" if dark else "light"
st.markdown(ui.css(theme), unsafe_allow_html=True)

st.title(T["title"])
st.caption(T["tagline"])

data, resource_rows = load_store(LOCAL or VOLUME)
tab_overview, tab_resources, tab_connections = st.tabs(
    [T["tab_overview"], T["tab_resources"], T["tab_connections"]]
)

# --- overview ------------------------------------------------------------------------------

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
                frame = pd.DataFrame(data["by_reading"])
                frame["reading"] = frame["reading"].map(lambda r: T.get(f"reading_{r}", r))
                st.altair_chart(chart(frame, "bar", "reading", "findings", theme), theme=None)
        with middle:
            st.subheader(T["by_owner"])
            owners = pd.DataFrame(data["by_owner"]).fillna({"monthly_cost": 0})
            if not owners.empty:
                st.altair_chart(
                    chart(owners, "bar", "owner", "monthly_cost", theme, horizontal=True),
                    theme=None,
                )
        with right:
            st.subheader(T["trend"])
            trend = pd.DataFrame(data["trend"])
            if not trend.empty:
                st.altair_chart(
                    chart(trend, "line", "started_at", "open_findings", theme), theme=None
                )

        st.subheader(T["findings"])
        findings = data["findings"]
        f1, f2, f3 = st.columns(3)
        readings = f1.multiselect(
            T["filter_reading"],
            sorted({f["reading"] for f in findings}),
            format_func=lambda r: T.get(f"reading_{r}", r),
        )
        groups = f2.multiselect(
            T["resource_group"], sorted({f["resource_group"] or "—" for f in findings})
        )
        names = f3.multiselect(
            T["filter_resource"], sorted({f["resource_name"] or "—" for f in findings})
        )
        shown = [
            f
            for f in findings
            if (not readings or f["reading"] in readings)
            and (not groups or (f["resource_group"] or "—") in groups)
            and (not names or (f["resource_name"] or "—") in names)
        ]
        st.markdown(
            f'<div class="cp-muted">{T["legend"]}</div>'
            + ui.legend(sorted({f["resource_group"] or "" for f in shown})),
            unsafe_allow_html=True,
        )
        number, size = pager("findings", len(shown), T)
        items, pages = ui.page(shown, number, size)
        st.markdown(
            "".join(
                ui.finding_card(
                    f,
                    T,
                    theme,
                    logic.parse_json(f["evidence"]),
                    logic.parse_json(f["coverage_notes"]),
                )
                for f in items
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="cp-muted">'
            + T["showing"].format(n=len(items), total=len(shown), page=number, pages=pages)
            + "</div>",
            unsafe_allow_html=True,
        )

# --- resources -----------------------------------------------------------------------------

with tab_resources:
    st.write(T["resources_help"])
    if resource_rows:
        st.session_state.setdefault(
            "choices", {r["resource_id"]: bool(r["selected"]) for r in resource_rows}
        )

        def leave_out() -> None:
            current = st.session_state["choices"]
            st.session_state["choices"] = logic.leave_out_nonproduction(
                [
                    {**r, "selected": current.get(r["resource_id"], r["selected"])}
                    for r in resource_rows
                ]
            )
            for key in [k for k in st.session_state if str(k).startswith("sel::")]:
                del st.session_state[key]

        def remember(resource_id: str) -> None:
            st.session_state["choices"][resource_id] = st.session_state[f"sel::{resource_id}"]

        top_left, top_right = st.columns([3, 1])
        top_left.button(T["leave_out_nonprod"], on_click=leave_out)
        selected_count = sum(st.session_state["choices"].values())
        top_right.markdown(
            '<div class="cp-muted">'
            + T["selected_count"].format(n=selected_count, total=len(resource_rows))
            + "</div>",
            unsafe_allow_html=True,
        )
        ordered = sorted(
            resource_rows,
            key=lambda r: (r["subscription"], r["resource_group"], r["kind"], r["name"]),
        )
        number, size = pager("resources", len(ordered), T, sizes=(20, 50, 100))
        items, _ = ui.page(ordered, number, size)
        current_group = None
        for r in items:
            group = r["resource_group"]
            if group != current_group:
                current_group = group
                st.markdown(
                    f'<div class="cp-muted"><i class="cp-dot" style="background:{ui.color_for(group)}"></i>'
                    f"{T['resource_group']}: <b>{html.escape(group)}</b> · "
                    f"{html.escape(r['subscription'])}</div>",
                    unsafe_allow_html=True,
                )
            c1, c2, c3 = st.columns([1, 4, 3])
            c1.toggle(
                T["analyze"],
                value=st.session_state["choices"].get(r["resource_id"], bool(r["selected"])),
                key=f"sel::{r['resource_id']}",
                on_change=remember,
                args=(r["resource_id"],),
                label_visibility="collapsed",
            )
            kind = T["workspace"] if r["kind"] == "workspace" else T["storage"]
            managed = (
                f" · {T['managed_by']}: {html.escape(r['managed_by'])}" if r["managed_by"] else ""
            )
            c2.markdown(
                f'<div class="cp-row"><b>{html.escape(r["name"])}</b>'
                f'<div class="cp-muted">{kind}{managed}</div></div>',
                unsafe_allow_html=True,
            )
            env = r["environment"] or "unknown"
            c3.markdown(
                ui.badge(T.get(f"env_{env}", env), ui.ENV_COLORS.get(env, "#dee2e6"))
                + f'<span class="cp-muted">{T["suggested_by"]}: '
                f"{html.escape(r['environment_source'] or '—')}</span>",
                unsafe_allow_html=True,
            )
        if st.button(T["save"], type="primary"):
            current = json.loads(read_bytes("selection.json") or b"{}")
            write_text(
                "selection.json",
                json.dumps(
                    logic.apply_selection(current, dict(st.session_state["choices"]), user_email()),
                    indent=2,
                ),
            )
            st.success(T["saved"])

# --- connections ---------------------------------------------------------------------------

with tab_connections:
    st.write(T["connections_help"])
    health = data.get("health") or []
    chosen = [h for h in health if h["selected"]]
    if chosen:
        status_labels = {"ok": T["ready"], "error": T["missing"], None: T["not_scanned"]}
        rows = [
            [
                h["name"],
                T["workspace"] if h["kind"] == "workspace" else T["storage"],
                T.get(f"env_{h['environment']}", h["environment"] or "—"),
                status_labels.get(h["last_scan_status"], h["last_scan_status"]),
                (h["last_scan_error"] or "")[:160],
            ]
            for h in chosen
        ]
        st.markdown(
            ui.table([T["name"], T["kind"], T["environment"], T["status"], T["detail"]], rows),
            unsafe_allow_html=True,
        )
        st.download_button(
            T["download_script"],
            logic.access_script(health, resource_rows, IDENTITY),
            file_name="cosmosproof-access.sh",
        )
