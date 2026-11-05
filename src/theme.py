"""Shared design system for the HHX analytics dashboard.

Single source of truth for the visual identity: colors, typography,
the custom Plotly template (``hhx_dark``) and the global CSS blob the
app injects. Everything visual — charts, cards, sidebar, buttons —
should derive from this module rather than hard-coding values.

Design contract:
- Tinted dark surfaces on a near-black page, never pure black.
- One accent (amber, the electricity theme); lime/danger used sparingly.
- Subtle 1px borders instead of heavy shadows.
- Outfit for UI and chart text, JetBrains Mono for numerals.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

TEMPLATE_NAME = "hhx_dark"

COLORS: dict[str, str] = {
    "bg": "#0B0E14",
    "surface": "#131720",
    "surface2": "#1A2230",
    "sidebar_bg": "#0E1220",
    "border": "rgba(148,163,184,0.14)",
    "text": "#E7ECF3",
    "muted": "#98A6B3",
    "accent": "#F59E0B",
    "positive": "#A3E635",
    "danger": "#F87171",
    "grid": "#1E2633",
    "accent_04": "rgba(245,158,11,0.04)",
    "accent_08": "rgba(245,158,11,0.08)",
    "accent_20": "rgba(245,158,11,0.20)",
    "accent_55": "rgba(245,158,11,0.55)",
    "accent_60": "rgba(245,158,11,0.60)",
}

SERIES_PALETTE: list[str] = [
    "#F59E0B",
    "#A3E635",
    "#38BDF8",
    "#F472B6",
    "#C084FC",
    "#FBBF24",
    "#34D399",
]

FONT_UI = "Outfit, 'Segoe UI', system-ui, sans-serif"
FONT_MONO = "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace"

FONT_CSS = """\
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --hhx-bg: #0B0E14;
  --hhx-surface: #131720;
  --hhx-surface-2: #1A2230;
  --hhx-sidebar-bg: #0E1220;
  --hhx-border: rgba(148,163,184,0.14);
  --hhx-text: #E7ECF3;
  --hhx-muted: #98A6B3;
  --hhx-accent: #F59E0B;
  --hhx-positive: #A3E635;
  --hhx-danger: #F87171;
  --hhx-grid: #1E2633;
  --hhx-font-ui: 'Outfit', 'Segoe UI', system-ui, sans-serif;
  --hhx-font-mono: 'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace;
}
"""


def register_plotly_theme() -> None:
    """Build and register the ``hhx_dark`` Plotly template. Idempotent."""
    if TEMPLATE_NAME in pio.templates:
        return

    axis = dict(
        gridcolor=COLORS["grid"],
        gridwidth=1,
        zeroline=False,
        linecolor=COLORS["grid"],
        linewidth=1,
        ticks="outside",
        ticklen=4,
        tickcolor=COLORS["grid"],
        tickfont=dict(family=FONT_MONO, size=11, color=COLORS["muted"]),
        title=dict(font=dict(family=FONT_UI, size=12, color=COLORS["muted"]), standoff=8),
    )

    layout = go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=COLORS["surface"],
        font=dict(family=FONT_UI, size=13, color=COLORS["text"]),
        colorway=SERIES_PALETTE,
        margin=dict(l=48, r=24, t=56, b=44),
        title=dict(
            x=0,
            xanchor="left",
            pad=dict(t=8),
            font=dict(family=FONT_UI, size=16, weight=600, color=COLORS["text"]),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            font=dict(family=FONT_UI, size=12, color=COLORS["text"]),
        ),
        hoverlabel=dict(
            bgcolor=COLORS["surface2"],
            bordercolor=COLORS["border"],
            font=dict(family=FONT_UI, size=13, color=COLORS["text"]),
            align="left",
        ),
        xaxis=axis,
        yaxis=axis,
    )
    pio.templates[TEMPLATE_NAME] = go.layout.Template(layout=layout)


def apply_plotly_theme(fig: go.Figure) -> go.Figure:
    """Apply the ``hhx_dark`` template to ``fig`` and return it."""
    fig.update_layout(template=TEMPLATE_NAME, hovermode="closest")
    return fig


def get_base_css() -> str:
    """Global CSS injected by the app: variables, surfaces, components."""
    css = FONT_CSS + """
/* ---------- app shell ---------- */
body, [data-testid="stApp"] {
  background-color: var(--hhx-bg);
  background-image: radial-gradient(
    ellipse 1100px 520px at 50% -180px,
    rgba(245,158,11,0.04),
    transparent 70%
  );
  background-attachment: fixed;
  color: var(--hhx-text);
  font-family: var(--hhx-font-ui);
}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] {
  background-color: var(--hhx-sidebar-bg);
  border-right: 1px solid var(--hhx-border);
  color: var(--hhx-text);
}

/* ---------- content block padding ---------- */
.block-container {
  padding-top: 1.5rem;
  padding-bottom: 3rem;
}

/* ---------- typography ---------- */
h1, h2, h3, h4, h5, h6,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 {
  font-family: var(--hhx-font-ui);
  letter-spacing: -0.02em;
  color: var(--hhx-text);
}

.section-header {
  font-family: var(--hhx-font-ui);
  font-size: 1.05rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--hhx-text);
  margin: 0 0 0.15rem 0;
}

.section-sub {
  font-family: var(--hhx-font-ui);
  font-size: 0.82rem;
  color: var(--hhx-muted);
  margin: 0;
}

/* ---------- KPI / metric cards ---------- */
.kpi-card {
  background: var(--hhx-surface);
  border: 1px solid var(--hhx-border);
  border-radius: 12px;
  padding: 16px 20px;
  box-shadow: 0 1px 2px rgba(11,14,20,0.4), 0 8px 24px rgba(245,158,11,0.05);
}

.kpi-card .kpi-label {
  font-family: var(--hhx-font-ui);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--hhx-muted);
  margin: 0 0 8px 0;
}

.kpi-card .kpi-value {
  font-family: var(--hhx-font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 28px;
  font-weight: 600;
  line-height: 1.15;
  color: var(--hhx-text);
  margin: 0;
}

.kpi-card .delta-up { color: var(--hhx-positive); }
.kpi-card .delta-down { color: var(--hhx-danger); }

[data-testid="stMetric"] {
  background: var(--hhx-surface);
  border: 1px solid var(--hhx-border);
  border-radius: 12px;
  padding: 14px 18px;
}

[data-testid="stMetricLabel"] p {
  font-family: var(--hhx-font-ui);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--hhx-muted);
}

[data-testid="stMetricValue"] {
  font-family: var(--hhx-font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 26px;
  font-weight: 600;
}

/* ---------- buttons ---------- */
.stButton > button,
.stDownloadButton > button,
[data-testid="baseButton-primary"],
[data-testid="baseButton-secondary"],
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"] {
  background: var(--hhx-surface);
  border: 1px solid var(--hhx-border);
  color: var(--hhx-text);
  border-radius: 10px;
  font-family: var(--hhx-font-ui);
  font-weight: 500;
  transition: background-color 200ms ease, border-color 200ms ease, transform 120ms ease;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="baseButton-primary"]:hover,
[data-testid="baseButton-secondary"]:hover,
[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-secondary"]:hover {
  background: var(--hhx-surface-2);
  border-color: rgba(245,158,11,0.35);
  color: var(--hhx-text);
}

.stButton > button:active,
.stDownloadButton > button:active,
[data-testid="baseButton-primary"]:active,
[data-testid="baseButton-secondary"]:active,
[data-testid="stBaseButton-primary"]:active,
[data-testid="stBaseButton-secondary"]:active {
  transform: scale(0.98);
}

.stButton > button:focus-visible,
.stDownloadButton > button:focus-visible,
[data-testid="baseButton-primary"]:focus-visible,
[data-testid="baseButton-secondary"]:focus-visible,
[data-testid="stBaseButton-primary"]:focus-visible,
[data-testid="stBaseButton-secondary"]:focus-visible {
  outline: 2px solid var(--hhx-accent);
  outline-offset: 2px;
}

/* ---------- dataframe ---------- */
[data-testid="stDataFrame"] {
  background-color: var(--hhx-surface);
  border: 1px solid var(--hhx-border);
  border-radius: 12px;
  overflow: hidden;
}

/* ---------- tabs ---------- */
[data-testid="stTabs"] [role="tablist"] {
  gap: 6px;
  border-bottom: 1px solid var(--hhx-border);
  margin-top: 14px;
}

[data-testid="stTabs"] [role="tab"] {
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 8px 14px;
  color: var(--hhx-muted);
  font-family: var(--hhx-font-ui);
  font-weight: 500;
  transition: background-color 200ms ease, color 200ms ease, box-shadow 200ms ease;
}

[data-testid="stTabs"] [role="tab"]:hover {
  background: var(--hhx-surface-2);
  color: var(--hhx-text);
}

[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  background: var(--hhx-surface);
  border-color: var(--hhx-border);
  color: var(--hhx-text);
  box-shadow: inset 0 -2px 0 var(--hhx-accent);
}

/* ---------- plotly charts ---------- */
.js-plotly-plot,
.js-plotly-plot .plot-container,
.js-plotly-plot .svg-container {
  background: transparent !important;
}

/* ---------- plotly modebar: dark pill, dims until plot hover ---------- */
.modebar {
  background: rgba(19, 23, 32, 0.88) !important;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 8px;
}
.modebar-container {
  opacity: 0.5;
  transition: opacity 180ms ease;
}
.js-plotly-plot:hover .modebar-container,
.modebar-container:hover {
  opacity: 1;
}
.modebar-group {
  background: transparent !important;
  border-left: 1px solid rgba(148, 163, 184, 0.12);
}
.modebar-group:first-child {
  border-left: none;
}
.modebar-btn {
  background-color: transparent;
  color: var(--hhx-muted);
}
.modebar-btn svg path {
  fill: var(--hhx-muted) !important;
}
.modebar-btn:hover,
.modebar-btn.active {
  background-color: rgba(26, 34, 48, 0.9);
}
.modebar-btn:hover svg path,
.modebar-btn.active svg path {
  fill: var(--hhx-accent) !important;
}

/* ---------- alerts: neutralize default info-blue ---------- */
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) {
  background: transparent !important;
  border: none !important;
}
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) [data-testid="stAlertContainer"] {
  background: var(--hhx-surface) !important;
  border: 1px solid var(--hhx-border) !important;
  border-radius: 12px;
}
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) p,
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) li,
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) [data-testid="stMarkdownContainer"] {
  color: var(--hhx-muted) !important;
}
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) strong,
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) h4 {
  color: var(--hhx-text) !important;
}

/* ---------- date-picker popover hardening ---------- */
[data-testid="stDateInputCalendar"] {
  background-color: var(--hhx-surface) !important;
  border: 1px solid var(--hhx-border);
  border-radius: 12px;
}
[data-testid="stDateInputCalendar"] [role="gridcell"] [role="button"][data-selected="true"],
[data-testid="stDateInputCalendar"] [role="gridcell"] [role="button"][data-focused="true"] {
  border-color: var(--hhx-accent) !important;
  color: var(--hhx-accent) !important;
}

/* ---------- widget popover panels (react-aria portals) ---------- */
div[data-testid="stDateInputCalendar"],
div[data-testid="stDateInputCalendar"] > div {
  color: var(--hhx-text);
}

/* ---------- scrollbars ---------- */
* {
  scrollbar-width: thin;
  scrollbar-color: rgba(148,163,184,0.25) transparent;
}

::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: rgba(148,163,184,0.25);
  border-radius: 8px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(148,163,184,0.4);
}

/* ---------- reduced motion ---------- */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition: none !important;
    animation: none !important;
  }
}
"""
    return css


register_plotly_theme()
