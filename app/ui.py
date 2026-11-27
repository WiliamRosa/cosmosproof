"""Presentation helpers for the CosmosProof app: themes, pastel colors, cards and pages.

Pure functions that return CSS and HTML strings, so they can be tested without a browser.
Every value that comes from the customer's metadata goes through `html.escape`.
"""

from __future__ import annotations

import hashlib
import html
import math

THEMES = {
    "light": {
        "bg": "#f6f7f9",
        "card": "#ffffff",
        "text": "#1f2328",
        "muted": "#6b7280",
        "border": "#e5e7eb",
        "tint": 0.55,
        "sidebar": "#eef0f3",
    },
    "dark": {
        "bg": "#0f1419",
        "card": "#171d24",
        "text": "#e6edf3",
        "muted": "#9aa4b2",
        "border": "#2b333c",
        "tint": 0.18,
        "sidebar": "#131920",
    },
}

# Pastel colors for resource groups, picked by a stable hash of the group name.
PASTELS = [
    "#a5d8ff",  # blue
    "#b2f2bb",  # green
    "#ffd8a8",  # orange
    "#d0bfff",  # violet
    "#ffec99",  # yellow
    "#fcc2d7",  # pink
    "#99e9f2",  # cyan
    "#c3fae8",  # teal
    "#eebefa",  # grape
    "#dee2e6",  # gray
]
READING_COLORS = {"cost": "#ffd8a8", "risk": "#ffc9c9", "compliance": "#d0bfff"}
CONFIDENCE_COLORS = {"high": "#b2f2bb", "medium": "#ffec99", "low": "#dee2e6"}
ENV_COLORS = {
    "prod": "#b2f2bb",
    "dev": "#a5d8ff",
    "test": "#ffec99",
    "poc": "#d0bfff",
    "unknown": "#dee2e6",
}
CHART_PALETTE = ["#74c0fc", "#8ce99a", "#ffc078", "#b197fc", "#ffe066", "#faa2c1", "#66d9e8"]


def color_for(group: str | None) -> str:
    if not group:
        return PASTELS[-1]
    digest = hashlib.sha256(group.lower().encode()).digest()
    return PASTELS[digest[0] % (len(PASTELS) - 1)]


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def css(theme: str) -> str:
    t = THEMES[theme]
    return f"""
<style>
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
  background: {t["bg"]}; color: {t["text"]};
}}
[data-testid="stSidebar"] {{ background: {t["sidebar"]}; }}
.stApp p, .stApp span, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp li,
[data-testid="stMetricValue"], [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"] {{
  color: {t["text"]} !important;
}}
[data-testid="stMetric"] {{
  background: {t["card"]}; border: 1px solid {t["border"]}; border-radius: 12px;
  padding: 14px 16px;
}}
.stTabs [data-baseweb="tab-list"] {{ border-bottom-color: {t["border"]}; }}
.cp-muted {{ color: {t["muted"]}; font-size: 0.85rem; }}
.cp-card {{
  border: 1px solid {t["border"]}; border-left-width: 6px; border-radius: 10px;
  padding: 10px 14px; margin: 0 0 10px 0; color: {t["text"]};
}}
.cp-card summary {{ cursor: pointer; list-style: none; }}
.cp-card summary::-webkit-details-marker {{ display: none; }}
.cp-title {{ font-weight: 600; word-break: break-all; }}
.cp-meta {{ color: {t["muted"]}; font-size: 0.82rem; margin-top: 4px; }}
.cp-body {{ margin-top: 8px; font-size: 0.9rem; }}
.cp-body ul {{ margin: 4px 0 8px 18px; padding: 0; }}
.cp-badge {{
  display: inline-block; border-radius: 999px; padding: 1px 9px; margin-right: 6px;
  font-size: 0.75rem; font-weight: 600;
}}
/* Badges sit on pastel backgrounds in both themes: their text stays black, overriding the
   theme rule that colors every span. */
.stApp span.cp-badge {{ color: #1f2328 !important; }}
.cp-proof {{ font-family: ui-monospace, monospace; font-size: 0.75rem; color: {t["muted"]};
  word-break: break-all; }}
.cp-legend span {{ display: inline-block; margin: 0 12px 6px 0; font-size: 0.82rem; }}
.cp-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px;
  margin-right: 5px; vertical-align: middle; }}
.cp-row {{ border-bottom: 1px solid {t["border"]}; padding: 6px 0; }}
.cp-table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; color: {t["text"]}; }}
.cp-table th, .cp-table td {{ border-bottom: 1px solid {t["border"]}; padding: 8px 6px;
  text-align: left; vertical-align: top; }}
.cp-table th {{ color: {t["muted"]}; font-weight: 600; }}
</style>
"""


def badge(text: str, color: str) -> str:
    return f'<span class="cp-badge" style="background:{color}">{html.escape(text)}</span>'


def legend(groups: list[str]) -> str:
    items = "".join(
        f'<span><i class="cp-dot" style="background:{color_for(g)}"></i>{html.escape(g or "—")}</span>'
        for g in groups
    )
    return f'<div class="cp-legend">{items}</div>'


def finding_card(f: dict, labels: dict, theme: str, evidence: list, notes: list) -> str:
    color = color_for(f.get("resource_group"))
    tint = _rgba(color, THEMES[theme]["tint"])
    cost = (
        f" · {f['monthly_cost']:,.2f} {html.escape(f.get('currency') or '')}"
        if f.get("monthly_cost") is not None
        else ""
    )
    size = f" · {f['size_bytes'] / 1024**2:,.1f} MB" if f.get("size_bytes") else ""
    reading = f.get("reading") or ""
    head = (
        badge(labels.get(f"reading_{reading}", reading), READING_COLORS.get(reading, "#dee2e6"))
        + badge(f.get("confidence") or "", CONFIDENCE_COLORS.get(f.get("confidence"), "#dee2e6"))
        + f'<span class="cp-title">{html.escape(f.get("asset") or "")}</span>'
    )
    meta = (
        f"{html.escape(f.get('kind') or '')} · {labels['owner']}: "
        f"{html.escape(f.get('owner') or '—')} · {html.escape(f.get('resource_name') or '—')}"
        f" ({html.escape(f.get('resource_group') or '—')}){html.escape(cost)}{html.escape(size)}"
    )
    ev = "".join(
        f"<li>{html.escape(e.get('source', ''))}: {html.escape(e.get('signal', ''))}"
        + (f" ({html.escape(e['observed_at'][:10])})" if e.get("observed_at") else "")
        + "</li>"
        for e in evidence
    )
    nt = "".join(f"<li>{html.escape(n)}</li>" for n in notes)
    body = (
        f'<div class="cp-body"><b>{labels["recommendation"]}:</b> '
        f"{html.escape(f.get('recommendation') or '')}"
        f"<br><b>{labels['evidence']}:</b><ul>{ev}</ul>"
        + (f"<b>{labels['not_seen']}:</b><ul>{nt}</ul>" if nt else "")
        + f'<div class="cp-proof">{labels["proof"]}: {html.escape(f.get("proof_hash") or "")}</div></div>'
    )
    return (
        f'<details class="cp-card" style="background:{tint};border-left-color:{color}">'
        f'<summary><div>{head}</div><div class="cp-meta">{meta}</div></summary>{body}</details>'
    )


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>" for row in rows
    )
    return f'<table class="cp-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def page(items: list, page_number: int, page_size: int) -> tuple[list, int]:
    """Returns the items of a 1-based page and the number of pages (at least 1)."""
    pages = max(1, math.ceil(len(items) / page_size))
    current = min(max(page_number, 1), pages)
    start = (current - 1) * page_size
    return items[start : start + page_size], pages
