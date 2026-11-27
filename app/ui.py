"""Presentation helpers for the CosmosProof app, following the Cosmos Semantic console patterns
(slate palette, sky accent, Inter, rounded cards, pill badges with a dot, table footer pagination).

Pure functions that return CSS and HTML strings, so they can be tested without a browser.
Every value that comes from the customer's metadata goes through `html.escape`.
"""

from __future__ import annotations

import hashlib
import html
import math

# Tailwind slate scale, as in the Cosmos Semantic console.
THEMES = {
    "light": {
        "bg": "#f8fafc",  # slate-50
        "card": "#ffffff",
        "text": "#0f172a",  # slate-900
        "muted": "#64748b",  # slate-500
        "border": "#e2e8f0",  # slate-200
        "hover": "#f1f5f9",  # slate-100
        "accent": "#0284c7",  # sky-600
        "sidebar": "#f1f5f9",
        "tint": 0.22,
    },
    "dark": {
        "bg": "#020617",  # slate-950
        "card": "#0f172a",  # slate-900
        "text": "#f1f5f9",  # slate-100
        "muted": "#94a3b8",  # slate-400
        "border": "#1e293b",  # slate-800
        "hover": "#1e293b",
        "accent": "#38bdf8",  # sky-400
        "sidebar": "#0b1220",  # brand navy
        "tint": 0.10,
    },
}

# Pill badges: (light background, light text, light ring, dark background, dark text, dark ring,
# dot). The console's status tones, plus sky and violet.
TONES = {
    "emerald": ("#ecfdf5", "#065f46", "#a7f3d0", "#022c22", "#a7f3d0", "#065f46", "#10b981"),
    "amber": ("#fffbeb", "#78350f", "#fde68a", "#451a03", "#fde68a", "#92400e", "#f59e0b"),
    "rose": ("#fff1f2", "#9f1239", "#fecdd3", "#4c0519", "#fecdd3", "#9f1239", "#f43f5e"),
    "slate": ("#f1f5f9", "#334155", "#e2e8f0", "#1e293b", "#cbd5e1", "#334155", "#94a3b8"),
    "sky": ("#f0f9ff", "#075985", "#bae6fd", "#082f49", "#bae6fd", "#075985", "#0ea5e9"),
    "violet": ("#f5f3ff", "#5b21b6", "#ddd6fe", "#2e1065", "#ddd6fe", "#5b21b6", "#8b5cf6"),
}
READING_TONES = {"cost": "amber", "risk": "rose", "compliance": "violet"}
CONFIDENCE_TONES = {"high": "emerald", "medium": "amber", "low": "slate"}
ENV_TONES = {"prod": "emerald", "dev": "sky", "test": "amber", "poc": "violet", "unknown": "slate"}

# Pastel colors for resource groups, picked by a stable hash of the group name.
PASTELS = [
    "#7dd3fc",  # sky-300
    "#6ee7b7",  # emerald-300
    "#fcd34d",  # amber-300
    "#c4b5fd",  # violet-300
    "#f9a8d4",  # pink-300
    "#5eead4",  # teal-300
    "#fdba74",  # orange-300
    "#a5b4fc",  # indigo-300
    "#bef264",  # lime-300
    "#cbd5e1",  # slate-300, for "no group"
]
CHART_PALETTE = ["#38bdf8", "#34d399", "#fbbf24", "#a78bfa", "#f472b6", "#2dd4bf", "#fb923c"]


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
    dark = theme == "dark"
    pills = "\n".join(
        f".stApp span.cp-pill-{name} {{ background: {v[3] if dark else v[0]}; "
        f"color: {v[4] if dark else v[1]} !important; "
        f"box-shadow: inset 0 0 0 1px {v[5] if dark else v[2]}; }}\n"
        f".cp-pill-{name} .cp-pill-dot {{ background: {v[6]}; }}"
        for name, v in TONES.items()
    )
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;800&display=swap');
.stApp, .stApp * {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI",
  Roboto, Arial, sans-serif; }}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
  background: {t["bg"]}; color: {t["text"]};
}}
[data-testid="stSidebar"] {{ background: {t["sidebar"]}; border-right: 1px solid {t["border"]}; }}
.stApp p, .stApp span, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp li,
[data-testid="stMetricValue"], [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"] {{
  color: {t["text"]} !important;
}}
.stApp h2, .stApp h3 {{ font-weight: 600; letter-spacing: -0.01em; }}
[data-testid="stMetric"] {{
  background: {t["card"]}; border: 1px solid {t["border"]}; border-radius: 12px;
  padding: 16px; box-shadow: 0 1px 2px rgba(15,23,42,0.04);
}}
[data-testid="stMetricLabel"] p {{ font-size: 0.75rem; font-weight: 500; color: {t["muted"]} !important; }}
[data-testid="stMetricValue"] {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
.stTabs [data-baseweb="tab-list"] {{ border-bottom: 1px solid {t["border"]}; gap: 4px; }}
.stTabs [aria-selected="true"] p {{ color: {t["accent"]} !important; font-weight: 600; }}
.cp-muted {{ color: {t["muted"]} !important; font-size: 0.82rem; }}
.cp-list {{ background: {t["card"]}; border: 1px solid {t["border"]}; border-radius: 12px;
  overflow: hidden; box-shadow: 0 1px 2px rgba(15,23,42,0.04); }}
.cp-card {{ border-bottom: 1px solid {t["border"]}; border-left: 4px solid transparent;
  padding: 12px 16px; color: {t["text"]}; }}
.cp-card:last-child {{ border-bottom: 0; }}
.cp-card:hover {{ filter: brightness({0.98 if not dark else 1.15}); }}
.cp-card summary {{ cursor: pointer; list-style: none; }}
.cp-card summary::-webkit-details-marker {{ display: none; }}
.cp-eyebrow {{ font-size: 0.68rem; font-weight: 600; letter-spacing: 0.06em;
  text-transform: uppercase; color: {t["muted"]}; }}
.cp-title {{ font-weight: 600; color: {t["accent"]}; word-break: break-all; }}
.cp-meta {{ color: {t["muted"]}; font-size: 0.82rem; margin-top: 2px; }}
.cp-body {{ margin-top: 10px; font-size: 0.88rem; line-height: 1.55; }}
.cp-body ul {{ margin: 4px 0 8px 18px; padding: 0; }}
.cp-pill {{ display: inline-flex; align-items: center; gap: 5px; border-radius: 999px;
  padding: 1px 9px; margin-right: 6px; font-size: 0.72rem; font-weight: 600;
  white-space: nowrap; }}
.cp-pill-dot {{ width: 6px; height: 6px; border-radius: 999px; display: inline-block; }}
{pills}
.cp-proof {{ font-family: ui-monospace, SFMono-Regular, monospace !important; font-size: 0.72rem;
  color: {t["muted"]}; word-break: break-all; }}
.cp-legend span {{ display: inline-block; margin: 0 12px 6px 0; font-size: 0.8rem; }}
.cp-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px;
  margin-right: 5px; vertical-align: middle; }}
.cp-row {{ padding: 4px 0; }}
.cp-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; color: {t["text"]};
  background: {t["card"]}; border: 1px solid {t["border"]}; border-radius: 12px; overflow: hidden; }}
.cp-table th {{ font-size: 0.75rem; font-weight: 500; color: {t["muted"]}; text-align: left;
  padding: 10px 16px; border-bottom: 1px solid {t["border"]}; }}
.cp-table td {{ padding: 12px 16px; border-bottom: 1px solid {t["border"]}; vertical-align: top; }}
.cp-table tr:last-child td {{ border-bottom: 0; }}
.cp-footer {{ color: {t["muted"]}; font-size: 0.85rem; font-variant-numeric: tabular-nums;
  padding-top: 8px; }}
[class*="st-key-"][class*="_prev"] button, [class*="st-key-"][class*="_next"] button {{
  border-radius: 8px; border: 1px solid {t["border"]}; background: {t["card"]};
  color: {t["text"]}; min-height: 32px; padding: 0 10px;
}}
</style>
"""


def pill(text: str, tone: str) -> str:
    tone = tone if tone in TONES else "slate"
    return (
        f'<span class="cp-pill cp-pill-{tone}"><i class="cp-pill-dot"></i>'
        f"{html.escape(text)}</span>"
    )


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
        f" · {f['monthly_cost']:,.2f} {f.get('currency') or ''}"
        if f.get("monthly_cost") is not None
        else ""
    )
    size = f" · {f['size_bytes'] / 1024**2:,.1f} MB" if f.get("size_bytes") else ""
    reading = f.get("reading") or ""
    confidence = f.get("confidence") or ""
    eyebrow = f"{html.escape(f.get('kind') or '')} · {html.escape(f.get('resource_group') or '—')}"
    pills = pill(
        labels.get(f"reading_{reading}", reading), READING_TONES.get(reading, "slate")
    ) + pill(confidence, CONFIDENCE_TONES.get(confidence, "slate"))
    meta = (
        f"{labels['owner']}: {html.escape(f.get('owner') or '—')} · "
        f"{html.escape(f.get('resource_name') or '—')}{html.escape(cost)}{html.escape(size)}"
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
        f'<summary><div class="cp-eyebrow">{eyebrow}</div>'
        f'<div>{pills}<span class="cp-title">{html.escape(f.get("asset") or "")}</span></div>'
        f'<div class="cp-meta">{meta}</div></summary>{body}</details>'
    )


def card_list(cards: list[str]) -> str:
    return f'<div class="cp-list">{"".join(cards)}</div>'


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>" for row in rows
    )
    return f'<table class="cp-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def range_label(page_number: int, page_size: int, total: int, template: str) -> str:
    """ "1–25 of 44", as in the console's table footer."""
    if total == 0:
        return template.format(start=0, end=0, total=0)
    start = (page_number - 1) * page_size + 1
    return template.format(start=start, end=min(start + page_size - 1, total), total=total)


def page(items: list, page_number: int, page_size: int) -> tuple[list, int]:
    """Returns the items of a 1-based page and the number of pages (at least 1)."""
    pages = max(1, math.ceil(len(items) / page_size))
    current = min(max(page_number, 1), pages)
    start = (current - 1) * page_size
    return items[start : start + page_size], pages
