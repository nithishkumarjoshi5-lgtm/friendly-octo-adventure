"""Plotly-based chart builders for the analytics app.

Contract: every public function returns a ``plotly.graph_objects.Figure``
styled with the shared ``hhx_dark`` theme (see ``src.theme``), with
left-aligned titles, muted axis labels and mono numerals on ticks.
Functions tolerate empty inputs by returning a themed placeholder figure
instead of raising. Rendering to bytes requires the optional ``kaleido``
engine; when it is missing, ``figure_to_bytes`` returns empty bytes.
"""

from __future__ import annotations

import datetime as _dt

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from . import theme

_MAX_POINTS = 10_000
_MAX_LABELED_BARS = 12
_MAX_FILL_POINTS = 2_000
_TS_RENDER_POINTS = 2_000
_TICK_THIN_THRESHOLD = 60
_MAX_X_TICKS = 10


def _style(
    fig: go.Figure,
    title: str | None,
    x_title: str | None = None,
    y_title: str | None = None,
) -> go.Figure:
    """Apply the shared theme plus consistent title/axis treatment."""
    theme.apply_plotly_theme(fig)
    if title:
        fig.update_layout(
            title=dict(
                text=title,
                x=0,
                xanchor="left",
                pad=dict(t=8),
                font=dict(
                    family=theme.FONT_UI,
                    size=16,
                    weight=600,
                    color=theme.COLORS["text"],
                ),
            )
        )
    if x_title:
        fig.update_xaxes(
            title_text=x_title,
            title_font=dict(family=theme.FONT_UI, size=12, color=theme.COLORS["muted"]),
        )
    if y_title:
        fig.update_yaxes(
            title_text=y_title,
            title_font=dict(family=theme.FONT_UI, size=12, color=theme.COLORS["muted"]),
        )
    return fig


def _empty_fig(title: str | None) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text="No data available",
        showarrow=False,
        font=dict(family=theme.FONT_UI, size=14, color=theme.COLORS["muted"]),
    )
    return _style(fig, title)


def _format_value(v) -> str:
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _add_bar_labels(trace: go.Bar, y_values) -> None:
    """Muted mono value labels, only when there are few bars."""
    if len(y_values) > _MAX_LABELED_BARS:
        return
    trace.text = [_format_value(v) for v in y_values]
    trace.textposition = "outside"
    trace.cliponaxis = False
    trace.textfont = dict(
        family=theme.FONT_MONO, size=11, color=theme.COLORS["muted"]
    )


def _probe_value(values):
    """First value of a sequence/Series, or None when empty."""
    if isinstance(values, (pd.Series, pd.Index)):
        return values.iloc[0] if len(values) else None
    for v in values:
        return v
    return None


def _is_datetime_like(values) -> bool:
    if isinstance(values, (pd.Series, pd.Index)):
        return bool(pd.api.types.is_datetime64_any_dtype(values))
    probe = _probe_value(values)
    return isinstance(probe, (pd.Timestamp, _dt.datetime, np.datetime64))


def _is_numeric_like(values) -> bool:
    if isinstance(values, (pd.Series, pd.Index)):
        return bool(pd.api.types.is_numeric_dtype(values))
    probe = _probe_value(values)
    return isinstance(probe, (int, float, np.integer, np.floating)) and not isinstance(
        probe, bool
    )


def _thin_x_ticks(fig: go.Figure, x_values) -> None:
    """Thin x-axis tick labels when there are many discrete values.

    Only categorical (string/object) axes need help: plotly renders one
    rotated, unreadable label per category beyond ~a few dozen values, while
    date and numeric axes thin themselves nicely in auto tick mode. Beyond
    ``_TICK_THIN_THRESHOLD`` categories, keep ~``_MAX_X_TICKS`` evenly spaced
    labels at a flat angle instead.
    """
    try:
        n = len(x_values)
    except TypeError:
        return
    if n <= _TICK_THIN_THRESHOLD or _is_datetime_like(x_values) or _is_numeric_like(x_values):
        return
    vals = list(x_values)
    k = min(_MAX_X_TICKS, n)
    positions = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    fig.update_xaxes(
        tickmode="array",
        tickvals=[vals[p] for p in positions],
        tickangle=0,
    )


def plot_time_series(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    """Line chart of ``y`` over ``x``, sorted by ``x`` and downsampled.

    Dense series are capped well below the hover-rendering budget so the
    trace reads as line texture instead of a solid mass; the zero-fill is
    reserved for sparse series where it does not saturate.
    """
    if df is None or df.empty or x not in df.columns or y not in df.columns:
        return _empty_fig(title)
    data = df.sort_values(x)
    if len(data) > _MAX_POINTS:
        step = (len(data) + _MAX_POINTS - 1) // _MAX_POINTS
        data = data.iloc[::step]
    if len(data) > _TS_RENDER_POINTS:
        step = (len(data) + _TS_RENDER_POINTS - 1) // _TS_RENDER_POINTS
        data = data.iloc[::step]
    trace_kwargs: dict = dict(
        x=data[x],
        y=data[y],
        mode="lines",
        name=y,
        line=dict(color=theme.COLORS["accent"], width=1.6),
        opacity=0.9,
        hovertemplate=f"%{{x}}<br>%{{y:,.2f}} {y}<extra></extra>",
    )
    # Fill reads as a solid blob on dense series — only fill sparse ones.
    if len(data) < _MAX_FILL_POINTS:
        trace_kwargs["fill"] = "tozeroy"
        trace_kwargs["fillcolor"] = theme.COLORS["accent_04"]
    fig = go.Figure(go.Scatter(**trace_kwargs))
    _thin_x_ticks(fig, data[x])
    return _style(fig, title, x_title=x, y_title=y)


def plot_bar(
    x, y, title: str, labels: dict[str, str] | None = None
) -> go.Figure:
    """Bar chart from iterables; ``labels`` maps ``'x'``/``'y``' to axis titles."""
    y_values = list(y)
    fig = go.Figure(
        go.Bar(
            x=list(x),
            y=y_values,
            marker=dict(color=theme.COLORS["accent"], cornerradius=6),
        )
    )
    _add_bar_labels(fig.data[0], y_values)
    labels = labels or {}
    return _style(fig, title, x_title=labels.get("x"), y_title=labels.get("y"))


def plot_line(
    x, y, title: str, labels: dict[str, str] | None = None
) -> go.Figure:
    """Line chart from iterables; ``labels`` maps ``'x'``/``'y``' to axis titles."""
    x_vals = list(x)
    fig = go.Figure(
        go.Scatter(
            x=x_vals,
            y=list(y),
            mode="lines",
            line=dict(color=theme.COLORS["accent"], width=1.6),
            opacity=0.9,
        )
    )
    _thin_x_ticks(fig, x_vals)
    labels = labels or {}
    return _style(fig, title, x_title=labels.get("x"), y_title=labels.get("y"))


def plot_hourly_profile(hourly_df: pd.DataFrame) -> go.Figure:
    """Bar chart of average kW per hour of day from a DataFrame(hour, avg_kw)."""
    title = "Average power by hour of day"
    if hourly_df is None or hourly_df.empty or not {"hour", "avg_kw"} <= set(hourly_df.columns):
        return _empty_fig(title)
    fig = go.Figure(
        go.Bar(
            x=hourly_df["hour"],
            y=hourly_df["avg_kw"],
            marker=dict(color=theme.COLORS["accent"], cornerradius=6),
        )
    )
    _add_bar_labels(fig.data[0], list(hourly_df["avg_kw"]))
    return _style(fig, title, x_title="Hour of day", y_title="Avg kW")


def plot_monthly_trend(monthly_df: pd.DataFrame) -> go.Figure:
    """Line + markers of monthly kWh from a DataFrame(year_month, kwh)."""
    title = "Monthly energy consumption"
    if monthly_df is None or monthly_df.empty or not {"year_month", "kwh"} <= set(monthly_df.columns):
        return _empty_fig(title)
    fig = go.Figure(
        go.Scatter(
            x=monthly_df["year_month"],
            y=monthly_df["kwh"],
            mode="lines+markers",
            line=dict(color=theme.COLORS["accent"], width=2),
            marker=dict(
                size=8,
                color=theme.COLORS["surface"],
                line=dict(color=theme.COLORS["accent"], width=2),
            ),
            hovertemplate="%{x}<br>%{y:,.2f} kWh<extra></extra>",
        )
    )
    return _style(fig, title, x_title="Month", y_title="kWh")


def plot_submetering(sub_df: pd.DataFrame) -> go.Figure:
    """Bar chart of total kWh per sub meter from a DataFrame(sub_metering, total_kwh, pct_of_total)."""
    title = "Energy by sub metering"
    if sub_df is None or sub_df.empty or not {"sub_metering", "total_kwh"} <= set(sub_df.columns):
        return _empty_fig(title)
    has_pct = "pct_of_total" in sub_df.columns
    fig = go.Figure(
        go.Bar(
            x=sub_df["sub_metering"],
            y=sub_df["total_kwh"],
            marker=dict(color=theme.COLORS["accent"], cornerradius=6),
            customdata=sub_df["pct_of_total"] if has_pct else None,
            hovertemplate="%{x}<br>%{y:.2f} kWh"
            + (" (%{customdata:.1f}%)" if has_pct else "")
            + "<extra></extra>",
        )
    )
    _add_bar_labels(fig.data[0], list(sub_df["total_kwh"]))
    return _style(fig, title, x_title="Sub metering", y_title="Total kWh")


def plot_correlation_heatmap(corr_df: pd.DataFrame) -> go.Figure:
    """Correlation heatmap via ``px.imshow`` with fixed -1..1 color range."""
    title = "Correlation heatmap"
    if corr_df is None or corr_df.empty:
        return _empty_fig(title)
    diverging_scale = [
        [0.0, "#1E3A8A"],
        [0.35, "#22304A"],
        [0.5, "#10151F"],
        [0.65, "#3A2C14"],
        [1.0, "#B45309"],
    ]
    fig = px.imshow(
        corr_df,
        text_auto=".2f",
        color_continuous_scale=diverging_scale,
        zmin=-1,
        zmax=1,
    )
    fig.update_traces(
        textfont=dict(family=theme.FONT_MONO, size=11, color="#E7ECF3"),
        xgap=2,
        ygap=2,
        hovertemplate="%{x} / %{y}<br>%{z:.2f}<extra></extra>",
    )
    fig.update_coloraxes(
        colorbar=dict(
            outlinewidth=0,
            thickness=12,
            ticklen=3,
            tickfont=dict(family=theme.FONT_MONO, size=11, color=theme.COLORS["muted"]),
        )
    )
    fig = _style(fig, title)
    fig.update_layout(margin=dict(l=8, r=8, t=56, b=8))
    return fig


def plot_histogram(series, bins: int = 50, title: str | None = None) -> go.Figure:
    """Histogram of a numeric series."""
    if series is None or len(series) == 0:
        return _empty_fig(title)
    fig = go.Figure(
        go.Histogram(
            x=series,
            nbinsx=bins,
            marker=dict(
                color=theme.COLORS["accent_60"],
                line=dict(color=theme.COLORS["surface"], width=1),
            ),
        )
    )
    name = getattr(series, "name", None)
    return _style(fig, title or "Distribution", x_title=str(name) if name else None, y_title="Count")


def plot_box(series, title: str | None = None) -> go.Figure:
    """Box plot of a numeric series."""
    title = title or "Box plot"
    if series is None or len(series) == 0:
        return _empty_fig(title)
    name = getattr(series, "name", None)
    fig = go.Figure(
        go.Box(
            y=series,
            name=str(name) if name else "value",
            fillcolor=theme.COLORS["accent_20"],
            line=dict(color=theme.COLORS["accent"], width=1.5),
            marker=dict(color=theme.COLORS["accent"], size=5, opacity=0.8),
        )
    )
    return _style(fig, title, y_title=str(name) if name else None)


def plot_scatter(df: pd.DataFrame, x: str, y: str, sample: int = 5000) -> go.Figure:
    """Scatter plot of ``y`` vs ``x``; random-samples to ``sample`` rows (random_state=42)."""
    title = f"{y} vs {x}"
    if df is None or df.empty or x not in df.columns or y not in df.columns:
        return _empty_fig(title)
    data = df.sample(n=sample, random_state=42) if len(df) > sample else df
    fig = go.Figure(
        go.Scatter(
            x=data[x],
            y=data[y],
            mode="markers",
            marker=dict(size=5, opacity=0.55, color=theme.COLORS["accent"]),
            hovertemplate=f"%{{x}}<br>%{{y:,.2f}}<extra></extra>",
        )
    )
    return _style(fig, title, x_title=x, y_title=y)


def recommend_chart_types(col_type_a: str, col_type_b: str | None = None) -> list[str]:
    """Recommend chart types for one or two column types.

    ``col_type_*`` must be one of "numeric", "categorical", "datetime",
    "identifier", "text". Identifier/text columns are never chartable.
    """
    valid = {"numeric", "categorical", "datetime", "identifier", "text"}
    if col_type_a not in valid or (col_type_b is not None and col_type_b not in valid):
        return []
    types = {col_type_a, col_type_b or col_type_a}
    if types & {"identifier", "text"}:
        return []
    if col_type_b is None:
        return {
            "numeric": ["histogram", "box"],
            "categorical": ["bar"],
            "datetime": ["line"],
        }.get(col_type_a, [])
    pair = types
    if pair == {"numeric", "numeric"}:
        return ["scatter", "histogram"]
    if pair == {"numeric", "datetime"}:
        return ["line", "scatter"]
    if pair == {"numeric", "categorical"}:
        return ["box", "bar"]
    if pair == {"categorical", "categorical"}:
        return ["bar"]
    if pair == {"datetime", "datetime"}:
        return ["line"]
    return []


def figure_to_bytes(fig: go.Figure, fmt: str = "png") -> bytes:
    """Serialize a figure to image bytes; empty bytes if no rendering engine."""
    try:
        return fig.to_image(format=fmt, scale=2)
    except Exception:
        return b""
