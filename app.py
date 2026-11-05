"""Household Electricity Analytics — interactive Streamlit dashboard.

This app is the presentation layer of the Big Data course project. It is a
single-script, six-page dashboard (page selected in the sidebar) sharing one
session-scoped dataset:

    1. Overview              — KPI cards, quality warnings, pipeline explainer.
    2. Data Explorer         — filters, search, cleaning controls, preview.
    3. Statistical Analysis  — summaries, frequencies, correlations, outliers.
    4. Electricity Analysis  — power trends, profiles, peaks (gated page).
    5. Custom Visualization  — pick any columns and chart them.
    6. Reports & Downloads   — CSV / stats / quality / markdown / PNG exports.

Session-state model:
    df          raw DataFrame exactly as loaded
    df_norm     normalized (lowercase columns) + datetime-parsed DataFrame
    df_view     df_norm after Explorer filters/cleaning (rebuilt every run)
    meta        file metadata dict from data_loader.get_file_metadata
    validation  validate_dataframe summary computed once at load time
    quality     logs of cleaning operations applied from the Explorer page

Datasets enter through the sidebar: bundled samples, a validated CSV upload,
or a pipeline-produced Parquet file from data/processed. Heavy electricity
computations are wrapped in @st.cache_data and keyed on a cheap content
fingerprint (row count, first timestamp, power sum) instead of hashing the
whole DataFrame.
"""

from __future__ import annotations

import glob
import html
import io
import os
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data_cleaning import (
    duplicate_summary,
    handle_duplicates,
    handle_missing,
    missing_value_summary,
    quality_warnings,
)
from src.data_loader import (
    get_file_metadata,
    infer_column_types,
    load_csv,
    load_sample_dataset,
    parse_datetime_columns,
)
from src.data_validation import (
    is_electricity_dataset,
    normalize_electricity_columns,
    validate_csv_upload,
    validate_dataframe,
)
from src.electricity_analytics import (
    compare_periods,
    compute_daily_pattern,
    compute_hourly_profile,
    compute_monthly_pattern,
    energy_kwh,
    high_consumption_periods,
    power_stats,
    submetering_comparison,
    voltage_current_stats,
)
from src.export_reports import (
    export_consolidated_report,
    export_dataframe_csv,
    export_quality_report,
    export_stats_report,
)
from src.general_analytics import (
    categorical_frequencies,
    correlation_matrix,
    numeric_summary,
    outlier_summary,
)
# Hot-reload the visualization module on rerun (mirrors the theme reload in
# the defensive block below) so chart styling tweaks show up live.
from src import visualization as _viz_module

import importlib as _importlib

_importlib.reload(_viz_module)

from src.visualization import (
    figure_to_bytes,
    plot_bar,
    plot_box,
    plot_correlation_heatmap,
    plot_histogram,
    plot_hourly_profile,
    plot_line,
    plot_monthly_trend,
    plot_scatter,
    plot_submetering,
    plot_time_series,
    recommend_chart_types,
)

st.set_page_config(
    page_title="Household Electricity Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Theme -----------------------------------------------------------------
# The shared theme module (src/theme.py) owns the base design tokens. Import
# defensively so the app still renders if the module is missing or incomplete.
try:
    from src import theme as _theme_module

    import importlib as _importlib

    _importlib.reload(_theme_module)
    _BASE_CSS: str = _theme_module.get_base_css()
except Exception:  # ImportError / missing get_base_css / signature drift
    _BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --vl-bg: #0B0E14;
  --vl-surface: #131720;
  --vl-surface-2: #1A2230;
  --vl-border: rgba(148, 163, 184, 0.14);
  --vl-text: #E7ECF3;
  --vl-muted: #98A6B3;
  --vl-accent: #F59E0B;
  --vl-positive: #A3E635;
  --vl-danger: #F87171;
}

html, body, .stApp, button, input, select, textarea, [data-baseweb] {
  font-family: "Outfit", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
code, pre, kbd {
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}

.stApp { background: var(--vl-bg); color: var(--vl-text); }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stMainBlockContainer"] { padding-top: 1.75rem; }

.stApp h1, .stApp h2, .stApp h3 {
  font-family: "Outfit", sans-serif;
  color: var(--vl-text);
  letter-spacing: -0.015em;
}
.stApp h3 { font-size: 1rem; font-weight: 600; }

[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li { color: var(--vl-text); }
[data-testid="stMarkdownContainer"] strong { color: var(--vl-text); font-weight: 600; }
[data-testid="stMarkdownContainer"] a { color: var(--vl-accent); }
[data-testid="stCaptionContainer"] { color: var(--vl-muted); }

[data-testid="stMarkdownContainer"] table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
[data-testid="stMarkdownContainer"] th {
  text-transform: uppercase; letter-spacing: 0.08em; font-size: 11px; font-weight: 600;
  color: var(--vl-muted); text-align: left; padding: 8px 12px;
  border-bottom: 1px solid var(--vl-border);
}
[data-testid="stMarkdownContainer"] td {
  padding: 8px 12px; color: var(--vl-text);
  border-bottom: 1px solid var(--vl-border);
}

hr { border: none; border-top: 1px solid var(--vl-border); }

[data-testid="stSidebar"] {
  background: var(--vl-surface);
  border-right: 1px solid var(--vl-border);
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: var(--vl-muted); }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p strong { color: var(--vl-text); }

[data-testid="stSidebar"] div[role="radiogroup"] {
  display: flex; flex-direction: column; gap: 3px;
}
[data-testid="stSidebar"] div[role="radiogroup"] > label {
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 7px 12px;
  margin: 0;
  color: var(--vl-muted);
  font: 500 13.5px/1.35 "Outfit", sans-serif;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
  background: var(--vl-surface-2);
  color: var(--vl-text);
}
[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
  background: rgba(245, 158, 11, 0.13);
  border-color: rgba(245, 158, 11, 0.32);
  color: var(--vl-text);
}
[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked)::before {
  content: "";
  width: 5px; height: 5px;
  border-radius: 999px;
  background: var(--vl-accent);
  margin-right: 2px;
}
[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-of-type { display: none; }

.stButton > button, .stDownloadButton > button {
  background: var(--vl-surface-2);
  color: var(--vl-text);
  border: 1px solid var(--vl-border);
  border-radius: 9px;
  font: 500 13.5px/1.2 "Outfit", sans-serif;
  padding: 7px 16px;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  background: var(--vl-surface-2);
  color: var(--vl-accent);
  border-color: rgba(245, 158, 11, 0.45);
}
.stButton > button[kind="primary"] {
  background: rgba(245, 158, 11, 0.16);
  color: var(--vl-accent);
  border-color: rgba(245, 158, 11, 0.4);
}
.stButton > button[kind="primary"]:hover {
  background: rgba(245, 158, 11, 0.24);
  color: var(--vl-accent);
  border-color: rgba(245, 158, 11, 0.55);
}

[data-baseweb="select"] > div,
[data-baseweb="textarea"],
[data-baseweb="base-input"],
[data-testid="stDateInputField"] {
  border-radius: 9px;
}
[data-baseweb="select"] > div,
[data-baseweb="base-input"] {
  border-color: var(--vl-border);
}
[data-baseweb="select"] > div:hover { border-color: rgba(245, 158, 11, 0.4); }

[data-testid="stFileUploaderDropzone"] {
  background: var(--vl-surface-2);
  border: 1px dashed rgba(148, 163, 184, 0.25);
  border-radius: 12px;
}
[data-testid="stFileUploaderDropzone"] button {
  background: rgba(245, 158, 11, 0.14);
  color: var(--vl-accent);
  border: 1px solid rgba(245, 158, 11, 0.35);
  border-radius: 8px;
}

[data-testid="stExpander"] details {
  background: var(--vl-surface);
  border: 1px solid var(--vl-border);
  border-radius: 12px;
  overflow: hidden;
}
[data-testid="stExpander"] summary {
  font: 500 13.5px/1.3 "Outfit", sans-serif;
  padding: 12px 16px;
  color: var(--vl-text);
}
[data-testid="stExpander"] svg { color: var(--vl-muted); }

[data-baseweb="tab-list"] {
  gap: 6px;
  border-bottom: 1px solid var(--vl-border);
}
[data-baseweb="tab"] {
  background: transparent;
  border-radius: 999px;
  padding: 6px 14px;
  margin-bottom: 6px;
  color: var(--vl-muted);
  font: 500 13.5px/1.2 "Outfit", sans-serif;
}
[data-baseweb="tab"] p { font-size: 13.5px; font-weight: 500; }
[data-baseweb="tab"]:hover { background: var(--vl-surface-2); color: var(--vl-text); }
[data-baseweb="tab"][aria-selected="true"] {
  background: rgba(245, 158, 11, 0.14);
  color: var(--vl-accent);
}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }

[data-testid="stDataFrame"] {
  border: 1px solid var(--vl-border);
  border-radius: 12px;
  overflow: hidden;
}

[data-testid="stAlert"] { border-radius: 12px; }
[data-testid="stSpinner"] { color: var(--vl-muted); }

div[data-testid="stCode"] {
  border: 1px solid var(--vl-border);
  border-radius: 12px;
  background: var(--vl-surface);
}

::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.16);
  border-radius: 999px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(148, 163, 184, 0.28); }
::selection { background: rgba(245, 158, 11, 0.28); }
</style>
"""

# Component-level CSS for pieces this app renders directly (KPI cards, headers,
# sidebar pill nav, empty state). Appended in both code paths so the layout
# never depends on the theme module's coverage.
_UI_CSS = """
<style>
.vl-app-header { display: flex; align-items: center; gap: 10px; padding: 2px 0 14px; }
.vl-app-name { font: 600 17px/1.2 "Outfit", sans-serif; color: #E7ECF3; letter-spacing: -0.01em; }
.vl-app-sub { font: 400 11.5px/1.4 "Outfit", sans-serif; color: #98A6B3; margin-top: 3px; }

[data-testid="stMainBlockContainer"], .block-container { padding-top: 5.25rem; }

[data-testid="stSidebar"] div[role="radiogroup"] {
  display: flex; flex-direction: column; gap: 3px;
}
[data-testid="stSidebar"] div[role="radiogroup"] > label {
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 7px 12px;
  margin: 0;
  color: #98A6B3;
  font: 500 13.5px/1.35 "Outfit", sans-serif;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
  background: #1A2230;
  color: #E7ECF3;
}
[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
  background: rgba(245, 158, 11, 0.13);
  border-color: rgba(245, 158, 11, 0.32);
  color: #E7ECF3;
}
[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked)::before {
  content: "";
  width: 5px; height: 5px;
  border-radius: 999px;
  background: #F59E0B;
  margin-right: 2px;
}
[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-of-type { display: none; }

.vl-section-label {
  display: flex; align-items: center; gap: 10px;
  margin: 16px 0 10px;
  font: 600 10.5px/1 "Outfit", sans-serif;
  letter-spacing: 0.14em; text-transform: uppercase;
  color: #98A6B3;
}
.vl-section-label::after { content: ""; flex: 1; height: 1px; background: rgba(148, 163, 184, 0.14); }

.vl-page-header { margin-bottom: 18px; }
.vl-page-title { font: 600 28px/1.15 "Outfit", sans-serif; letter-spacing: -0.02em; color: #E7ECF3; }
.vl-page-sub { font: 400 13.5px/1.5 "Outfit", sans-serif; color: #98A6B3; margin-top: 5px; }

.kpi-card {
  background: #131720;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 12px;
  padding: 16px;
  min-height: 96px;
  box-sizing: border-box;
  display: flex; flex-direction: column; justify-content: center;
}
.kpi-card.dense { padding: 14px 12px; min-height: 86px; }
.kpi-label {
  font: 600 10.5px/1.3 "Outfit", sans-serif;
  letter-spacing: 0.14em; text-transform: uppercase;
  color: #98A6B3;
  margin-bottom: 9px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kpi-value {
  font: 600 26px/1.15 "JetBrains Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  color: #E7ECF3;
  white-space: nowrap;
}
.kpi-card.dense .kpi-value { font-size: 22px; letter-spacing: -0.03em; }
.kpi-value.kpi-text {
  font-size: 14.5px; font-weight: 500; line-height: 1.4;
  white-space: normal; word-break: break-word; letter-spacing: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
@media (max-width: 1440px) {
  .kpi-card .kpi-value { font-size: 23px; }
  .kpi-card.dense .kpi-value { font-size: 20px; }
}
@media (max-width: 1280px) {
  .kpi-card { padding: 14px 16px; min-height: 90px; }
  .kpi-card.dense { min-height: 84px; }
  .kpi-card .kpi-value { font-size: 20px; }
  .kpi-card.dense .kpi-value { font-size: 18px; }
}
@media (max-width: 1140px) {
  .kpi-card, .kpi-card.dense { padding: 14px 8px; }
  .kpi-card .kpi-value { font-size: 16px; }
  .kpi-card.dense .kpi-value { font-size: 14px; }
}
.kpi-delta {
  margin-top: 8px;
  font: 500 12px/1.3 "JetBrains Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.kpi-delta.up { color: #A3E635; }
.kpi-delta.down { color: #F87171; }

.vl-empty {
  background: #131720;
  border: 1px dashed rgba(148, 163, 184, 0.28);
  border-radius: 12px;
  padding: 72px 32px;
  display: flex; flex-direction: column; align-items: center; text-align: center;
}
.vl-empty-icon { margin-bottom: 18px; opacity: 0.85; }
.vl-empty-title { font: 600 18px/1.3 "Outfit", sans-serif; color: #E7ECF3; }
.vl-empty-sub { font: 400 13.5px/1.6 "Outfit", sans-serif; color: #98A6B3; margin-top: 7px; }
</style>
"""

PAGE_SIZE = 500
MAX_CATEGORICAL_FILTERS = 4
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
SAMPLES: Dict[str, Tuple[str, str]] = {
    "Household Electricity": ("electricity", "data/raw/household_power_consumption.txt"),
    "Online Retail": ("online_retail", "data/raw/Online Retail.xlsx"),
}
_MISSING_OPTIONS = ["keep", "drop_rows", "fill_mean", "fill_median", "fill_mode"]
_DUPLICATE_OPTIONS = ["keep", "drop"]


def _init_state() -> None:
    defaults: Dict[str, Any] = {
        "df": None,
        "df_norm": None,
        "df_view": None,
        "meta": {},
        "validation": {},
        "quality": {},
        "clean_logs": [],
        "upload_sig": "",
        "upload_error": "",
        "filt_cats": {},
        "clean_missing": "keep",
        "clean_dupes": "keep",
        "elec_start": None,
        "elec_end": None,
        "cmp1_start": None,
        "cmp1_end": None,
        "cmp2_start": None,
        "cmp2_end": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _clear_filters() -> None:
    """Delete filter widget state (runs before widgets instantiate, e.g. in on_click) so they re-initialize to their defaults."""
    for key in ("filt_start", "filt_end", "filt_cols", "filt_search", "filt_cats"):
        st.session_state.pop(key, None)
    for key in [k for k in list(st.session_state) if str(k).startswith("cat_")]:
        st.session_state.pop(key, None)


def install_dataset(df_raw: pd.DataFrame, meta: Dict[str, Any]) -> None:
    """Normalize, parse and profile a freshly loaded dataset; reset all view filters."""
    df_norm = parse_datetime_columns(normalize_electricity_columns(df_raw))
    st.session_state["df"] = df_raw
    st.session_state["df_norm"] = df_norm
    st.session_state["df_view"] = df_norm
    st.session_state["meta"] = meta
    st.session_state["validation"] = validate_dataframe(df_norm)
    st.session_state["quality"] = {}
    st.session_state["clean_logs"] = []
    _clear_filters()
    st.session_state["clean_missing"] = "keep"
    st.session_state["clean_dupes"] = "keep"
    st.session_state["elec_start"] = None
    st.session_state["elec_end"] = None
    st.session_state["cmp1_start"] = None
    st.session_state["cmp1_end"] = None
    st.session_state["cmp2_start"] = None
    st.session_state["cmp2_end"] = None


@st.cache_data(show_spinner="Loading sample dataset…")
def load_sample_cached(name: str) -> pd.DataFrame:
    return load_sample_dataset(name)


@st.cache_data(show_spinner="Loading processed parquet…")
def load_parquet_cached(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


def _power_hash(df: pd.DataFrame) -> tuple:
    """Cheap content fingerprint (rows, columns, timestamp bounds, power sum) for cache keys."""
    try:
        ts_min = ts_max = 0.0
        if "datetime" in df.columns:
            mn, mx = df["datetime"].min(), df["datetime"].max()
            ts_min = float(mn.value) if pd.notna(mn) else 0.0
            ts_max = float(mx.value) if pd.notna(mx) else 0.0
        gp = 0.0
        if "global_active_power" in df.columns:
            gp = float(pd.to_numeric(df["global_active_power"], errors="coerce").sum())
        return (len(df), tuple(map(str, df.columns)), ts_min, ts_max, round(gp, 6))
    except Exception:
        return (len(df), (), 0.0, 0.0, 0.0)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_power_stats(df: pd.DataFrame) -> dict:
    return power_stats(df)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_hourly_profile(df: pd.DataFrame) -> pd.DataFrame:
    return compute_hourly_profile(df)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_daily_pattern(df: pd.DataFrame) -> pd.DataFrame:
    return compute_daily_pattern(df)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_monthly_pattern(df: pd.DataFrame) -> pd.DataFrame:
    return compute_monthly_pattern(df)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_submetering(df: pd.DataFrame) -> pd.DataFrame:
    return submetering_comparison(df)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_voltage_current(df: pd.DataFrame) -> dict:
    return voltage_current_stats(df)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_peaks(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    return high_consumption_periods(df, top_n=top_n)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_compare(
    df: pd.DataFrame, start1: str, end1: str, start2: str, end2: str
) -> dict:
    return compare_periods(df, start1, end1, start2, end2)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_export_csv(df: pd.DataFrame) -> bytes:
    return export_dataframe_csv(df)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_stats_report_bytes(df: pd.DataFrame) -> bytes:
    stats: Dict[str, Any] = {"Numeric Summary": numeric_summary(df)}
    for col, freq in categorical_frequencies(df, max_categories=20).items():
        stats[f"Categorical Frequencies — {col}"] = freq
    return export_stats_report(stats)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_quality_report_bytes(df: pd.DataFrame) -> bytes:
    quality: Dict[str, Any] = {
        "rows": len(df),
        "cols": df.shape[1],
        "completeness_pct": round(float(df.notna().sum().sum()) / max(1, df.size) * 100, 2),
        "missing": missing_value_summary(df),
        "duplicates": duplicate_summary(df),
        "warnings": quality_warnings(df),
    }
    return export_quality_report(quality)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_consolidated_bytes(df: pd.DataFrame, filename: str) -> bytes:
    quality: Dict[str, Any] = {
        "rows": len(df),
        "cols": df.shape[1],
        "completeness_pct": round(float(df.notna().sum().sum()) / max(1, df.size) * 100, 2),
        "missing": missing_value_summary(df),
        "duplicates": duplicate_summary(df),
        "warnings": quality_warnings(df),
    }
    overview: Dict[str, Any] = {
        "Dataset": filename,
        "Rows": f"{len(df):,}",
        "Columns": df.shape[1],
        "Completeness %": quality["completeness_pct"],
    }
    dt_col = first_datetime_col(df)
    if dt_col:
        ser = df[dt_col].dropna()
        if not ser.empty:
            overview["Date range"] = f"{ser.min():%Y-%m-%d} → {ser.max():%Y-%m-%d}"
    ctx: Dict[str, Any] = {
        "title": f"Household Electricity Analytics — {filename}",
        "overview": overview,
        "stats": {"Numeric summary": numeric_summary(df)},
        "quality": quality,
    }
    if is_electricity_dataset(df):
        elec_ctx: Dict[str, Any] = {}
        try:
            elec_ctx["Power stats"] = cached_power_stats(df)
        except Exception:
            pass
        try:
            elec_ctx["Sub-metering kWh"] = cached_submetering(df)
        except Exception:
            pass
        try:
            elec_ctx["Top 5 consumption days"] = cached_peaks(df, 5)
        except Exception:
            pass
        if elec_ctx:
            ctx["electricity"] = elec_ctx
    return export_consolidated_report(ctx)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_infer_column_types(df: pd.DataFrame) -> Dict[str, str]:
    return infer_column_types(df)


@st.cache_data(hash_funcs={pd.DataFrame: _power_hash}, show_spinner=False)
def cached_quality_warnings(df: pd.DataFrame) -> List[str]:
    return quality_warnings(df)


def first_datetime_col(df: pd.DataFrame) -> Optional[str]:
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col
    return None


def _fmt_num(value: Any, suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{float(value):,.2f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


_BOLT_SVG = (
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
    'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<path d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 11.25 13.5H3.75z" '
    'fill="#F59E0B"/></svg>'
)
_BOLT_MUTED_SVG = (
    '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" '
    'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<path d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 11.25 13.5H3.75z" '
    'fill="#3A4456"/></svg>'
)


def inject_theme_css() -> None:
    """Apply the dark dashboard CSS once, before any page content renders.

    theme.get_base_css() may return bare CSS (no <style> wrapper); wrap it so
    it applies instead of rendering as literal text.
    """
    # Assemble base + component CSS (visual layer only)
    base = _BASE_CSS.strip()
    if base and "<style" not in base.lower():
        base = f"<style>{base}</style>"
    st.markdown(base + _UI_CSS, unsafe_allow_html=True)


def _page_header(title: str, subtitle: str) -> None:
    st.markdown(
        '<div class="vl-page-header">'
        f'<div class="vl-page-title">{title}</div>'
        f'<div class="vl-page-sub">{subtitle}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def _section_label(text: str) -> None:
    st.markdown(
        f'<div class="vl-section-label">{text}</div>', unsafe_allow_html=True
    )


def _kpi(
    label: str,
    value: str,
    delta: Optional[str] = None,
    delta_direction: str = "up",
    dense: bool = False,
    text: bool = False,
) -> str:
    """Render one KPI card (surface bg, mono value, optional delta line)."""
    classes = "kpi-card dense" if dense else "kpi-card"
    value_classes = "kpi-value kpi-text" if text else "kpi-value"
    delta_html = ""
    if delta:
        direction = "up" if delta_direction == "up" else "down"
        delta_html = f'<div class="kpi-delta {direction}">{delta}</div>'
    if text:
        # Clamp long text values to 2 lines; keep the full text as a tooltip.
        title_attr = html.escape(value.replace("\u200b", ""), quote=True)
        value_html = f'<div class="{value_classes}" title="{title_attr}">{value}</div>'
    else:
        value_html = f'<div class="{value_classes}">{value}</div>'
    return (
        f'<div class="{classes}">'
        f'<div class="kpi-label">{label}</div>'
        f"{value_html}"
        f"{delta_html}</div>"
    )


def _kpi_row(slots: Sequence[Tuple[Any, str]]) -> None:
    """Place a sequence of (column, kpi html) pairs into existing columns."""
    for col, html in slots:
        col.markdown(html, unsafe_allow_html=True)


def _load_sample(key: str, path: str) -> None:
    try:
        raw = load_sample_cached(key)
    except Exception as exc:
        st.error(f"Could not load sample dataset: {exc}")
    else:
        install_dataset(raw, get_file_metadata(path, os.path.basename(path)))
        st.rerun()


def _handle_upload(upl: Any) -> None:
    """Validate and install an uploaded CSV (shared by sidebar + empty state)."""
    sig = f"{upl.name}|{upl.size}"
    if sig != st.session_state.get("upload_sig"):
        st.session_state["upload_sig"] = sig
        st.session_state["upload_error"] = ""
        if upl.size > MAX_UPLOAD_BYTES:
            st.session_state["upload_error"] = "File exceeds the 200 MB limit."
        else:
            ok, reason = validate_csv_upload(upl)
            if not ok:
                st.session_state["upload_error"] = reason
            else:
                try:
                    raw = load_csv(io.BytesIO(upl.getvalue()))
                    if raw.empty:
                        raise ValueError("the CSV contains no data rows")
                except Exception as exc:
                    st.session_state["upload_error"] = f"Could not parse CSV: {exc}"
                else:
                    install_dataset(raw, get_file_metadata(upl, upl.name))
                    st.rerun()


def render_empty_state() -> None:
    st.markdown(
        '<div class="vl-empty">'
        f'<div class="vl-empty-icon">{_BOLT_MUTED_SVG}</div>'
        '<div class="vl-empty-title">No dataset loaded</div>'
        '<div class="vl-empty-sub">'
        "Load the household electricity sample or upload a CSV to begin."
        "</div></div>",
        unsafe_allow_html=True,
    )
    a1, a2 = st.columns(2)
    with a1:
        if st.button("Load household sample", key="btn_empty_household", type="primary"):
            _load_sample("electricity", "data/raw/household_power_consumption.txt")
    with a2:
        st.caption("Or drop a CSV here (max 200 MB)")
        upl = st.file_uploader(
            "Upload CSV (max 200 MB)", type=["csv"], key="empty_uploader"
        )
        if upl is not None:
            _handle_upload(upl)
    err = st.session_state.get("upload_error")
    if err:
        st.error(f"Upload rejected: {err}")


def _stable_selectbox(label: str, options: List[str], state_key: str, default_index: int = 0) -> str:
    current = st.session_state.get(state_key)
    index = options.index(current) if current in options else default_index
    value = st.selectbox(label, options, index=index)
    st.session_state[state_key] = value
    return value


def _missing_bar_figure(view: pd.DataFrame) -> go.Figure:
    ms = missing_value_summary(view)
    ms = ms[ms["missing_pct"] > 0]
    if ms.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No missing values",
            showarrow=False,
            font=dict(size=18, color="#A3E635"),
        )
        fig.update_layout(title="Missing Values by Column (%)")
        _theme_module.apply_plotly_theme(fig)
        return fig
    return plot_bar(
        ms["column"],
        ms["missing_pct"],
        "Missing Values by Column (%)",
        labels={"x": "Column", "y": "Missing %"},
    )


def _downsample_frame(df: pd.DataFrame, max_points: int = 10_000) -> pd.DataFrame:
    if len(df) <= max_points:
        return df
    step = (len(df) + max_points - 1) // max_points
    return df.iloc[::step]


def _scatter_colored(df: pd.DataFrame, x: str, y: str, color: str, sample: int = 5000) -> go.Figure:
    data = df.dropna(subset=[x, y, color])
    top = data[color].astype(str).value_counts().head(12).index
    data = data[data[color].astype(str).isin(top)]
    data = data.sample(n=sample, random_state=42) if len(data) > sample else data
    fig = go.Figure()
    palette = _theme_module.SERIES_PALETTE
    for i, (value, group) in enumerate(data.groupby(data[color].astype(str))):
        fig.add_trace(
            go.Scatter(
                x=group[x],
                y=group[y],
                mode="markers",
                name=value,
                marker=dict(size=4, opacity=0.6, color=palette[i % len(palette)]),
            )
        )
    fig.update_layout(title=f"{y} vs {x} by {color}")
    _theme_module.apply_plotly_theme(fig)
    fig.update_xaxes(title_text=x)
    fig.update_yaxes(title_text=y)
    return fig


def _box_grouped(df: pd.DataFrame, num_col: str, cat_col: str) -> go.Figure:
    groups = df[[num_col, cat_col]].dropna()
    top = groups[cat_col].astype(str).value_counts().head(8).index
    fig = go.Figure()
    palette = _theme_module.SERIES_PALETTE
    for i, value in enumerate(top):
        series = groups.loc[groups[cat_col].astype(str) == value, num_col]
        fig.add_trace(go.Box(y=series, name=value, marker_color=palette[i % len(palette)]))
    fig.update_layout(title=f"{num_col} by {cat_col}")
    _theme_module.apply_plotly_theme(fig)
    fig.update_yaxes(title_text=num_col)
    return fig


def ensure_view() -> Optional[pd.DataFrame]:
    """Rebuild the filtered/cleaned view from df_norm and stash it in session state."""
    df = st.session_state.get("df_norm")
    if df is None:
        return None
    view = df

    dt_col = first_datetime_col(df)
    ds = st.session_state.get("filt_start")
    de = st.session_state.get("filt_end")
    if dt_col and ds and de:
        start_ts = pd.Timestamp(ds)
        end_ts = pd.Timestamp(de) + pd.Timedelta(days=1)
        view = view[(view[dt_col] >= start_ts) & (view[dt_col] < end_ts)]

    for col, chosen in (st.session_state.get("filt_cats") or {}).items():
        if col in view.columns and chosen:
            view = view[view[col].astype("string").isin(set(map(str, chosen)))]

    query = (st.session_state.get("filt_search") or "").strip()
    if query:
        text_cols = [
            c
            for c in view.columns
            if pd.api.types.is_object_dtype(view[c]) or pd.api.types.is_string_dtype(view[c])
        ]
        if text_cols:
            mask = pd.Series(False, index=view.index)
            for c in text_cols:
                mask |= view[c].astype("string").str.contains(query, case=False, regex=False, na=False)
            view = view[mask]

    selected = st.session_state.get("filt_cols")
    if selected:
        keep = [c for c in selected if c in view.columns]
        if keep:
            view = view[keep]

    miss_log: List[str] = []
    dup_log: List[str] = []
    try:
        view, miss_log = handle_missing(view, st.session_state.get("clean_missing", "keep"))
    except Exception as exc:
        miss_log = [f"Missing-value strategy failed: {exc}"]
    try:
        view, dup_log = handle_duplicates(view, st.session_state.get("clean_dupes", "keep"))
    except Exception as exc:
        dup_log = [f"Duplicate strategy failed: {exc}"]
    st.session_state["clean_logs"] = miss_log + dup_log

    st.session_state["df_view"] = view
    return view


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown(
            '<div class="vl-app-header">'
            f"{_BOLT_SVG}"
            "<div>"
            '<div class="vl-app-name">Voltage Lens</div>'
            '<div class="vl-app-sub">Household power analytics</div>'
            "</div></div>",
            unsafe_allow_html=True,
        )
        page = st.radio("Page", list(PAGES.keys()), label_visibility="collapsed")

        _section_label("Dataset")
        meta = st.session_state.get("meta") or {}
        val = st.session_state.get("validation") or {}
        if meta.get("filename"):
            st.markdown(f"**Current:** {meta['filename']}")
            st.caption(f"{meta.get('size_human', '?')} · {val.get('rows', 0):,} rows × {val.get('cols', 0)} cols")
        else:
            st.caption("No dataset loaded yet")

        for label, (key, path) in SAMPLES.items():
            if st.button(label, key=f"btn_sample_{key}"):
                _load_sample(key, path)

        upl = st.file_uploader("Upload CSV (max 200 MB)", type=["csv"])
        if upl is not None:
            _handle_upload(upl)
        err = st.session_state.get("upload_error")
        if err:
            st.error(f"Upload rejected: {err}")

        _section_label("Backend")
        with st.expander("Big Data Backend"):
            st.markdown(
                "This dashboard runs on a single machine with pandas for snappy "
                "interaction. Behind it, the **Big Data pipeline** uses Hadoop/HDFS, "
                "Hive, Pig and Spark: the scripts live in `hive/`, `spark/` and "
                "`pig/` and are orchestrated with `docker-compose.bigdata.yml`. "
                "Spark jobs process the raw household power data and write Parquet "
                "files to `data/processed/`, which this dashboard can load from the "
                "Project Overview page."
            )
            st.code("docs/BIGDATA_SETUP.md", language=None)
    return page


def page_overview() -> None:
    _page_header("Overview", "Dataset health, key metrics and the processing pipeline")
    df = st.session_state.get("df_norm")
    if df is None:
        render_empty_state()
        return

    val = st.session_state.get("validation") or validate_dataframe(df)
    meta = st.session_state.get("meta") or {}

    st.subheader("Dataset at a glance")
    cols = st.columns(5)
    _kpi_row([
        (cols[0], _kpi("Dataset", str(meta.get("filename", "—")).replace("_", "_\u200b"), text=True)),
        (cols[1], _kpi("Records", f"{val.get('rows', 0):,}")),
        (cols[2], _kpi("Columns", f"{val.get('cols', 0)}")),
        (cols[3], _kpi("Completeness", f"{val.get('completeness_pct', 0):.2f}%")),
        (cols[4], _kpi("Memory", f"{val.get('memory_mb', 0):.1f} MB")),
    ])

    dt_col = first_datetime_col(df)
    if dt_col:
        ser = df[dt_col].dropna()
        if not ser.empty:
            st.caption(f"Date range ({dt_col}): **{ser.min():%Y-%m-%d} → {ser.max():%Y-%m-%d}**")

    if is_electricity_dataset(df):
        try:
            stats = cached_power_stats(df)
            p1, p2, p3 = st.columns(3)
            _kpi_row([
                (p1, _kpi("Avg power", f"{stats['avg_kw']:.3f} kW")),
                (p2, _kpi("Max power", f"{stats['max_kw']:.3f} kW")),
                (p3, _kpi("Min power", f"{stats['min_kw']:.3f} kW")),
            ])
        except Exception as exc:
            st.caption(f"Power KPIs unavailable: {exc}")

    st.subheader("Data-quality warnings")
    issues = cached_quality_warnings(df)
    if issues:
        st.warning("\n".join(f"- {w}" for w in issues))
    else:
        st.success("No major data-quality issues detected.")

    st.subheader("What this dashboard analyses")
    st.markdown(
        """
| Page | Analysis |
|---|---|
| **Data Explorer** | Interactive filtering, search, missing-value & duplicate inspection and cleaning |
| **Statistical Analysis** | Numeric summaries, categorical frequencies, correlations, IQR outliers |
| **Electricity Analysis** | Power trends, hourly/weekday/monthly profiles, sub-metering, peaks, period comparison |
| **Custom Visualization** | Choose any columns and render the recommended chart |
| **Reports & Downloads** | CSV, statistics, quality and consolidated Markdown/PNG exports |
"""
    )

    st.subheader("Data processing pipeline")
    st.markdown(
        """
1. **Upload** — a CSV (≤ 200 MB) via the sidebar, a bundled sample, or a
   pipeline Parquet from `data/processed/`.
2. **Validate** — `validate_csv_upload` checks the file, `validate_dataframe`
   profiles rows, columns, completeness and memory.
3. **Clean** — column names normalized, datetimes parsed, missing values and
   duplicates handled with explicit, logged strategies.
4. **Analyze** — statistics, trends, peaks and correlations recomputed on every
   filter change.
5. **Visualize** — Plotly charts (time series, profiles, heatmaps, histograms).
6. **Export** — filtered CSV, stats/quality reports and a consolidated
   Markdown report.
"""
    )

    st.subheader("Load pipeline output (data/processed)")
    files = sorted(glob.glob("data/processed/*.parquet"))
    if not files:
        st.caption(
            "No `.parquet` files in `data/processed/` yet. Run the Hadoop/Spark "
            "pipeline (see Big Data Backend in the sidebar) to generate them."
        )
    else:
        pick = st.selectbox("Processed file", files)
        if st.button("Load processed parquet", key="btn_parquet"):
            try:
                pdf = load_parquet_cached(pick)
            except Exception as exc:
                st.error(f"Could not read parquet: {exc}")
            else:
                install_dataset(pdf, get_file_metadata(pick, os.path.basename(pick)))
                st.rerun()


def page_explorer() -> None:
    _page_header("Data Explorer", "Filter, search and clean the active dataset")
    df = st.session_state.get("df_norm")
    if df is None:
        render_empty_state()
        return

    st.subheader("Filters")
    dt_col = first_datetime_col(df)
    f1, f2 = st.columns(2)
    if dt_col:
        ser = df[dt_col].dropna()
        if ser.empty:
            st.session_state.pop("filt_start", None)
            st.session_state.pop("filt_end", None)
            st.caption("The datetime column contains no parseable dates.")
        else:
            dmin, dmax = ser.min().date(), ser.max().date()
            cur_s = st.session_state.get("filt_start") or dmin
            cur_e = st.session_state.get("filt_end") or dmax
            cur_s = min(max(cur_s, dmin), dmax)
            cur_e = min(max(cur_e, dmin), dmax)
            with f1:
                st.date_input("Start date", value=cur_s, min_value=dmin, max_value=dmax, key="filt_start")
            with f2:
                st.date_input("End date", value=cur_e, min_value=dmin, max_value=dmax, key="filt_end")
    else:
        st.session_state.pop("filt_start", None)
        st.session_state.pop("filt_end", None)
        st.caption("No datetime column detected — date filtering disabled.")

    st.multiselect(
        "Columns to keep",
        list(df.columns),
        default=st.session_state.get("filt_cols") or list(df.columns),
        key="filt_cols",
    )

    types = cached_infer_column_types(df)
    cat_cols = [c for c, t in types.items() if t == "categorical"][:MAX_CATEGORICAL_FILTERS]
    if cat_cols:
        st.markdown("**Categorical value filters**")
        cat_state = st.session_state.setdefault("filt_cats", {})
        cols = st.columns(min(len(cat_cols), MAX_CATEGORICAL_FILTERS))
        for i, col in enumerate(cat_cols):
            options = sorted(df[col].dropna().astype(str).unique().tolist())[:50]
            with cols[i % len(cols)]:
                chosen = st.multiselect(col, options, default=cat_state.get(col, []), key=f"cat_{col}")
            cat_state[col] = chosen

    st.text_input(
        "Search across text columns",
        value=st.session_state.get("filt_search", ""),
        placeholder="Case-insensitive substring…",
        key="filt_search",
    )

    st.button("Reset filters", key="btn_reset_filters", on_click=_clear_filters)

    st.subheader("Cleaning controls")
    c1, c2 = st.columns(2)
    with c1:
        m_idx = _MISSING_OPTIONS.index(st.session_state.get("clean_missing", "keep"))
        m_strategy = st.selectbox("Missing values strategy", _MISSING_OPTIONS, index=m_idx)
        st.session_state["clean_missing"] = m_strategy
    with c2:
        d_idx = _DUPLICATE_OPTIONS.index(st.session_state.get("clean_dupes", "keep"))
        d_strategy = st.selectbox("Duplicate rows strategy", _DUPLICATE_OPTIONS, index=d_idx)
        st.session_state["clean_dupes"] = d_strategy

    view = ensure_view()
    if view is None:
        render_empty_state()
        return

    logs = st.session_state.get("clean_logs") or []
    if logs:
        st.info("**Cleaning log**\n\n" + "\n".join(f"- {line}" for line in logs))
    else:
        st.caption("Cleaning strategies are set to `keep` — nothing applied yet.")

    total = len(df)
    dup = duplicate_summary(view)
    st.subheader("Preview")
    p1, p2, p3 = st.columns(3)
    _kpi_row([
        (p1, _kpi("Rows (filtered)", f"{len(view):,}")),
        (p2, _kpi("Rows (raw)", f"{total:,}")),
        (
            p3,
            _kpi(
                "Duplicate rows",
                f"{dup['duplicate_rows']:,}",
                delta=f"{dup['duplicate_pct']}% of view",
                delta_direction="down" if dup["duplicate_pct"] > 0 else "up",
            ),
        ),
    ])

    n_chunks = max(1, -(-len(view) // PAGE_SIZE))
    current = st.session_state.get("explorer_page", 1)
    page_no = st.selectbox(
        f"Page (chunks of {PAGE_SIZE} rows)",
        range(1, n_chunks + 1),
        index=min(current, n_chunks) - 1,
    )
    st.session_state["explorer_page"] = page_no
    chunk = view.iloc[(page_no - 1) * PAGE_SIZE : page_no * PAGE_SIZE]

    col_config: Dict[str, Any] = {}
    for c in chunk.columns:
        if pd.api.types.is_numeric_dtype(chunk[c]):
            col_config[c] = st.column_config.NumberColumn(format="%.4f")
        elif pd.api.types.is_datetime64_any_dtype(chunk[c]):
            col_config[c] = st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm:ss")
    st.dataframe(chunk, column_config=col_config, hide_index=True)

    st.download_button(
        "Download filtered data (CSV)",
        data=cached_export_csv(view),
        file_name="filtered_data.csv",
        mime="text/csv",
    )

    st.subheader("Missing values")
    st.dataframe(missing_value_summary(view), hide_index=True)
    st.plotly_chart(_missing_bar_figure(view))

    st.subheader("Column types")
    types_df = pd.DataFrame(
        {"column": list(types.keys()), "inferred_type": list(types.values())}
    )
    st.dataframe(types_df, hide_index=True)
    st.caption("Types are inferred with `infer_column_types` (numeric / datetime / identifier / categorical / text).")


def page_stats() -> None:
    _page_header("Statistical Analysis", "Summaries, frequencies, correlations and outliers")
    view = ensure_view()
    if view is None:
        render_empty_state()
        return
    if view.empty:
        st.warning("The current filters removed every row — relax them in the Data Explorer.")
        return
    st.caption(f"Analysing **{len(view):,} filtered rows** (updates live with Data Explorer filters).")

    st.subheader("Numeric summary")
    ns = numeric_summary(view)
    if ns.empty:
        st.info("No numeric columns in the current view.")
    else:
        st.dataframe(ns.reset_index().rename(columns={"index": "column"}), hide_index=True)

    st.subheader("Categorical frequencies")
    freqs = categorical_frequencies(view, max_categories=15)
    if not freqs:
        st.info("No categorical (text) columns in the current view.")
    else:
        chosen = _stable_selectbox("Categorical column", list(freqs.keys()), "stats_cat_col")
        freq = freqs[chosen]
        if freq.empty:
            st.caption("No non-null values for this column.")
        else:
            st.plotly_chart(
                plot_bar(
                    freq["value"].astype(str),
                    freq["count"],
                    f"Top {len(freq)} values — {chosen}",
                    labels={"x": chosen, "y": "Count"},
                )
            )
            st.dataframe(freq, hide_index=True)

    st.subheader("Correlations")
    corr = correlation_matrix(view)
    if corr.empty:
        st.info("At least two numeric columns are required for correlations.")
    else:
        st.plotly_chart(plot_correlation_heatmap(corr))

    st.subheader("Outliers (IQR method)")
    os_df = outlier_summary(view)
    if os_df.empty:
        st.info("No numeric columns to scan for outliers.")
    else:
        st.dataframe(os_df.reset_index().rename(columns={"index": "column"}), hide_index=True)
        col = _stable_selectbox("Box plot column", [c for c in ns.index] or list(os_df.index), "stats_outlier_col")
        st.plotly_chart(plot_box(view[col].dropna(), title=f"Box plot — {col}"))

    st.subheader("Missing values & duplicates")
    ms = missing_value_summary(view)
    st.dataframe(ms[ms["missing_count"] > 0], hide_index=True)
    dup = duplicate_summary(view)
    k1, k2, k3 = st.columns(3)
    _kpi_row([
        (k1, _kpi("Total rows", f"{dup['total_rows']:,}")),
        (k2, _kpi("Duplicate rows", f"{dup['duplicate_rows']:,}")),
        (k3, _kpi("Duplicate %", f"{dup['duplicate_pct']}%")),
    ])


def page_electricity() -> None:
    _page_header("Electricity Analysis", "Power, energy, voltage and peak behaviour")
    df_norm = st.session_state.get("df_norm")
    if df_norm is None:
        render_empty_state()
        return
    if not is_electricity_dataset(df_norm):
        st.info(
            "Electricity-specific analysis is available when the dataset contains "
            "household power columns (`global_active_power` plus a date/time column). "
            "Load the **Household Electricity** sample from the sidebar to enable this page."
        )
        return

    view = ensure_view()
    if view is None:
        render_empty_state()
        return
    if "datetime" not in view.columns or "global_active_power" not in view.columns:
        st.warning(
            "The current Data Explorer column selection removed `datetime` and/or "
            "`global_active_power`. Re-include them (or reset filters) to use this page."
        )
        return

    ser = view["datetime"].dropna()
    if ser.empty:
        st.warning("No parseable timestamps in the current view.")
        return
    dmin, dmax = ser.min().date(), ser.max().date()

    st.subheader("Date range")
    e1, e2 = st.columns(2)
    cur_s = st.session_state.get("elec_start") or dmin
    cur_e = st.session_state.get("elec_end") or dmax
    cur_s = min(max(cur_s, dmin), dmax)
    cur_e = min(max(cur_e, dmin), dmax)
    with e1:
        es = st.date_input("From", value=cur_s, min_value=dmin, max_value=dmax)
    with e2:
        ee = st.date_input("To", value=cur_e, min_value=dmin, max_value=dmax)
    st.session_state["elec_start"] = es
    st.session_state["elec_end"] = ee

    elec = view[(view["datetime"] >= pd.Timestamp(es)) & (view["datetime"] < pd.Timestamp(ee) + pd.Timedelta(days=1))]
    if elec.empty:
        st.warning("No rows in the selected date range.")
        return

    st.subheader("Key metrics")
    try:
        with st.spinner("Crunching power stats…"):
            stats = cached_power_stats(elec)
            vc = cached_voltage_current(elec)
            total_kwh = energy_kwh(elec["global_active_power"])
        k1, k2, k3, k4, k5, k6 = st.columns([1, 1, 1, 1.6, 1, 1])
        _kpi_row([
            (k1, _kpi("Avg power", f"{stats['avg_kw']:.3f} kW", dense=True)),
            (k2, _kpi("Max power", f"{stats['max_kw']:.3f} kW", dense=True)),
            (k3, _kpi("Min power", f"{stats['min_kw']:.3f} kW", dense=True)),
            (k4, _kpi("Total energy", f"{total_kwh:,.1f} kWh", dense=True)),
            (k5, _kpi("Avg voltage", f"{vc['avg_voltage']:.2f} V", dense=True)),
            (k6, _kpi("Avg current", f"{vc['avg_current']:.2f} A", dense=True)),
        ])
    except Exception as exc:
        st.error(f"Could not compute KPIs: {exc}")
        return

    trends, hourly_t, daily_t, monthly_t, sub_t, vc_t, peak_t, cmp_t = st.tabs(
        [
            "Trends",
            "Hourly",
            "Daily / Weekly",
            "Monthly",
            "Sub-metering",
            "Voltage & Current",
            "Peak Periods",
            "Compare Periods",
        ]
    )

    with trends:
        st.plotly_chart(
            plot_time_series(
                elec, "datetime", "global_active_power", "Global Active Power Over Time"
            )
        )
        st.caption("Auto-downsampled to ≤ 2,000 points so the trend reads as a clean line.")

    with hourly_t:
        with st.spinner("Profiling hours…"):
            hourly = cached_hourly_profile(elec)
        st.plotly_chart(plot_hourly_profile(hourly))
        if not hourly.empty:
            peak_hour = int(hourly.loc[hourly["avg_kw"].idxmax(), "hour"])
            st.caption(f"Peak hour: **{peak_hour}:00** with {hourly['avg_kw'].max():.3f} kW average.")
        st.dataframe(hourly, hide_index=True)

    with daily_t:
        daily = cached_daily_pattern(elec)
        st.plotly_chart(
            plot_bar(
                daily["weekday_name"],
                daily["avg_kw"],
                "Average Power by Weekday",
                labels={"x": "Weekday", "y": "Avg kW"},
            )
        )
        st.dataframe(daily, hide_index=True)

    with monthly_t:
        monthly = cached_monthly_pattern(elec)
        st.plotly_chart(plot_monthly_trend(monthly))
        st.dataframe(monthly, hide_index=True)

    with sub_t:
        sub_cols = [c for c in ("sub_metering_1", "sub_metering_2", "sub_metering_3") if c in elec.columns]
        if len(sub_cols) < 3:
            st.info("This dataset has no sub-metering columns (sub_metering_1..3).")
        else:
            sub = cached_submetering(elec)
            st.plotly_chart(plot_submetering(sub))
            st.dataframe(sub.style.format({"total_kwh": "{:.2f}", "pct_of_total": "{:.1f}%"}), hide_index=True)

    with vc_t:
        if "voltage" not in elec.columns or "global_intensity" not in elec.columns:
            st.info("Voltage / current columns are missing from this dataset.")
        else:
            vc_stats = cached_voltage_current(elec)
            v1, v2, v3, v4 = st.columns(4)
            _kpi_row([
                (v1, _kpi("Avg voltage", f"{vc_stats['avg_voltage']:.2f} V")),
                (v2, _kpi("Min voltage", f"{vc_stats['min_voltage']:.2f} V")),
                (v3, _kpi("Max voltage", f"{vc_stats['max_voltage']:.2f} V")),
                (v4, _kpi("Avg current", f"{vc_stats['avg_current']:.2f} A")),
            ])
            st.plotly_chart(plot_time_series(elec, "datetime", "voltage", "Voltage Over Time"))
            st.plotly_chart(plot_time_series(elec, "datetime", "global_intensity", "Global Intensity Over Time"))

    with peak_t:
        with st.spinner("Ranking peak days…"):
            peaks = cached_peaks(elec, 10)
    st.dataframe(peaks, hide_index=True)
    peaks_fig = plot_bar(
        peaks["date"].astype(str),
        peaks["kwh"],
        "Top 10 Days by Energy Consumption",
        labels={"x": "Date", "y": "kWh"},
    )
    peaks_fig.update_xaxes(type="category")
    st.plotly_chart(peaks_fig)

    with cmp_t:
        st.markdown("Pick two inclusive date ranges to compare energy consumption.")
        mid = dmin + (dmax - dmin) / 2
        r1s, r1e, r2s, r2e = st.columns(4)
        s1 = st.session_state.get("cmp1_start") or dmin
        e1v = st.session_state.get("cmp1_end") or mid
        s2 = st.session_state.get("cmp2_start") or (mid + timedelta(days=1))
        e2v = st.session_state.get("cmp2_end") or dmax
        s1 = min(max(s1, dmin), dmax)
        e1v = min(max(e1v, dmin), dmax)
        s2 = min(max(s2, dmin), dmax)
        e2v = min(max(e2v, dmin), dmax)
        with r1s:
            p1s = st.date_input("Period 1 start", value=s1, min_value=dmin, max_value=dmax)
        with r1e:
            p1e = st.date_input("Period 1 end", value=e1v, min_value=dmin, max_value=dmax)
        with r2s:
            p2s = st.date_input("Period 2 start", value=s2, min_value=dmin, max_value=dmax)
        with r2e:
            p2e = st.date_input("Period 2 end", value=e2v, min_value=dmin, max_value=dmax)
        st.session_state["cmp1_start"] = p1s
        st.session_state["cmp1_end"] = p1e
        st.session_state["cmp2_start"] = p2s
        st.session_state["cmp2_end"] = p2e
        try:
            with st.spinner("Comparing periods…"):
                cmp_res = cached_compare(elec, str(p1s), str(p1e), str(p2s), str(p2e))
            pct = cmp_res["pct_change"]
            has_pct = not pd.isna(pct)
            c1, c2, c3, c4, c5 = st.columns(5)
            _kpi_row([
                (c1, _kpi("Period 1 energy (kWh)", _fmt_num(cmp_res["period1_kwh"]))),
                (c2, _kpi("Period 2 energy (kWh)", _fmt_num(cmp_res["period2_kwh"]))),
                (
                    c3,
                    _kpi(
                        "Change (P1 vs P2)",
                        "—" if not has_pct else f"{pct:+.1f}%",
                        delta="P2 vs P1" if has_pct else None,
                        delta_direction="up" if has_pct and pct >= 0 else "down",
                    ),
                ),
                (c4, _kpi("Period 1 avg power (kW)", _fmt_num(cmp_res["period1_avg_kw"]))),
                (c5, _kpi("Period 2 avg power (kW)", _fmt_num(cmp_res["period2_avg_kw"]))),
            ])
        except Exception as exc:
            st.error(f"Comparison failed: {exc}")


def build_custom_figure(
    view: pd.DataFrame, chart: str, a: str, b: Optional[str], bins: int, color: Optional[str]
) -> go.Figure:
    types = cached_infer_column_types(view)
    if chart == "histogram":
        return plot_histogram(view[a], bins=bins, title=f"Distribution of {a}")
    if chart == "box":
        if b is not None and types.get(b) == "categorical" and types.get(a) == "numeric":
            return _box_grouped(view, a, b)
        return plot_box(view[a], title=f"Box plot — {a}")
    if chart == "scatter":
        if b is None:
            return plot_scatter(view, x=a, y=a)
        x, y = a, b
        if pd.api.types.is_datetime64_any_dtype(view[b]) and pd.api.types.is_numeric_dtype(view[a]):
            x, y = b, a
        if color:
            return _scatter_colored(view, x, y, color)
        return plot_scatter(view, x=x, y=y)
    if chart == "line":
        if b is None:
            ser = view[a].dropna()
            if pd.api.types.is_datetime64_any_dtype(ser):
                counts = ser.dt.floor("D").value_counts().sort_index()
                return plot_line(counts.index, counts.to_numpy(), f"Records per day — {a}",
                                 labels={"x": "Day", "y": "Count"})
            counts = ser.astype(str).value_counts().sort_index().head(10_000)
            return plot_line(counts.index.astype(str), counts.to_numpy(), f"Values — {a}",
                             labels={"x": a, "y": "Count"})
        x, y = a, b
        if pd.api.types.is_datetime64_any_dtype(view[b]) and not pd.api.types.is_datetime64_any_dtype(view[a]):
            x, y = b, a
        data = view[[x, y]].dropna().sort_values(x)
        data = _downsample_frame(data)
        return plot_line(data[x], data[y], f"{y} over {x}", labels={"x": x, "y": y})
    if chart == "bar":
        if b is None:
            counts = view[a].value_counts().head(30)
            return plot_bar(counts.index.astype(str), counts.to_numpy(), f"Value counts — {a}",
                            labels={"x": a, "y": "Count"})
        if types.get(a) == "numeric" and types.get(b) == "categorical":
            num_col, cat_col = a, b
        elif types.get(b) == "numeric" and types.get(a) == "categorical":
            num_col, cat_col = b, a
        else:
            pair = view.groupby([a, b]).size().sort_values(ascending=False).head(20)
            labels = [f"{ia} | {ib}" for ia, ib in pair.index]
            return plot_bar(labels, pair.to_numpy(), f"Top pairs {a} × {b}",
                            labels={"x": f"{a} | {b}", "y": "Count"})
        means = view.groupby(view[cat_col].astype(str))[num_col].mean().sort_values(ascending=False).head(30)
        return plot_bar(means.index, means.to_numpy(), f"Mean {num_col} by {cat_col}",
                        labels={"x": cat_col, "y": f"Mean {num_col}"})
    raise ValueError(f"Unsupported chart type: {chart!r}")


def page_custom_viz() -> None:
    _page_header("Custom Visualization", "Plot any two columns from the active view")
    view = ensure_view()
    if view is None:
        render_empty_state()
        return
    if view.empty:
        st.warning("The current filters removed every row — relax them in the Data Explorer.")
        return

    types = cached_infer_column_types(view)
    cols = list(view.columns)
    c1, c2 = st.columns(2)
    with c1:
        a = _stable_selectbox("Column A (required)", cols, "viz_col_a")
    with c2:
        b = _stable_selectbox("Column B (optional)", ["— None —"] + cols, "viz_col_b")
    b_col = None if b == "— None —" else b

    st.caption(
        f"Column A `{a}` → **{types.get(a, '?')}**"
        + (f"  ·  Column B `{b_col}` → **{types.get(b_col, '?')}**" if b_col else "  ·  Column B: none")
    )

    recs = recommend_chart_types(types.get(a, "text"), types.get(b_col) if b_col else None)
    if not recs:
        st.warning("These columns are not suitable for charting (identifier/text columns are excluded). Pick different columns.")
        return

    chart = st.radio("Chart type", recs, horizontal=True)
    bins = st.slider("Histogram bins", min_value=5, max_value=200, value=50)
    color = None
    if chart == "scatter" and b_col is not None:
        color = _stable_selectbox("Color by (optional)", ["— None —"] + cols, "viz_color")
        color = None if color == "— None —" else color

    try:
        fig = build_custom_figure(view, chart, a, b_col, bins, color)
    except Exception as exc:
        st.error(f"Could not build the chart: {exc}")
        return
    st.plotly_chart(fig)


def page_reports() -> None:
    _page_header("Reports & Downloads", "Export the active view as data, reports and images")
    view = ensure_view()
    if view is None:
        render_empty_state()
        return
    if view.empty:
        st.warning("The current filters removed every row — relax them in the Data Explorer.")
        return

    meta = st.session_state.get("meta") or {}
    stem = os.path.splitext(str(meta.get("filename", "dataset")))[0].replace(" ", "_")

    st.subheader("Dataset")
    st.download_button(
        "Download filtered dataset (CSV)",
        data=cached_export_csv(view),
        file_name=f"{stem}_filtered.csv",
        mime="text/csv",
    )

    st.subheader("Statistical summary")
    st.download_button(
        "Download statistics report (TXT)",
        data=cached_stats_report_bytes(view),
        file_name=f"{stem}_stats.txt",
        mime="text/plain",
    )

    st.subheader("Data-quality report")
    st.download_button(
        "Download quality report (TXT)",
        data=cached_quality_report_bytes(view),
        file_name=f"{stem}_quality.txt",
        mime="text/plain",
    )

    st.subheader("Consolidated Markdown report")
    with st.spinner("Assembling consolidated report…"):
        consolidated = cached_consolidated_bytes(view, str(meta.get("filename", "dataset")))
    st.download_button(
        "Download consolidated report (Markdown)",
        data=consolidated,
        file_name=f"{stem}_report.md",
        mime="text/markdown",
    )

    st.subheader("Chart as PNG")
    options: Dict[str, Callable[[], go.Figure]] = {
        "Missing values by column": lambda: _missing_bar_figure(view),
    }
    corr = correlation_matrix(view)
    if not corr.empty:
        options["Correlation heatmap"] = lambda: plot_correlation_heatmap(corr)
    df_norm = st.session_state.get("df_norm")
    if df_norm is not None and is_electricity_dataset(df_norm) and "datetime" in view.columns and "global_active_power" in view.columns:
        options["Hourly profile"] = lambda: plot_hourly_profile(cached_hourly_profile(view))
        options["Monthly energy trend"] = lambda: plot_monthly_trend(cached_monthly_pattern(view))
    if not options:
        st.caption("No charts available for the current view.")
        return
    choice = _stable_selectbox("Chart", list(options.keys()), "reports_png_chart")
    st.plotly_chart(options[choice]())
    png = figure_to_bytes(options[choice](), "png")
    if png:
        st.image(png)
        st.download_button(
            "Download PNG",
            data=png,
            file_name=f"{stem}_{choice.lower().replace(' ', '_')}.png",
            mime="image/png",
        )
    else:
        st.caption(
            "PNG export skipped — the optional `kaleido` rendering engine is not "
            "installed. The interactive chart above can still be explored and "
            "exported directly from its toolbar."
        )


PAGES: Dict[str, Callable[[], None]] = {
    "Overview": page_overview,
    "Data Explorer": page_explorer,
    "Statistical Analysis": page_stats,
    "Electricity Analysis": page_electricity,
    "Custom Visualization": page_custom_viz,
    "Reports & Downloads": page_reports,
}


def main() -> None:
    _init_state()
    inject_theme_css()
    page = render_sidebar()
    PAGES.get(page, page_overview)()


if __name__ == "__main__":
    main()
