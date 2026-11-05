"""Tests for src.visualization."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from src import visualization


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _hourly_df() -> pd.DataFrame:
    return pd.DataFrame({"hour": range(24), "avg_kw": np.linspace(0.5, 5.0, 24)})


def _monthly_df() -> pd.DataFrame:
    return pd.DataFrame(
        {"year_month": ["2024-01", "2024-02", "2024-03"], "kwh": [10.0, 12.0, 9.0]}
    )


def _submetering_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sub_metering": ["sub_metering_1", "sub_metering_2"],
            "total_kwh": [3.0, 5.0],
            "pct_of_total": [37.5, 62.5],
        }
    )


def _corr_df() -> pd.DataFrame:
    return pd.DataFrame(
        {"a": [1.0, 0.5], "b": [0.5, 1.0]}, index=["a", "b"]
    )


# ---------------------------------------------------------------------------
# plot builders
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "builder"),
    [
        (
            "plot_time_series",
            lambda: visualization.plot_time_series(
                pd.DataFrame({"t": range(10), "v": range(10)}), "t", "v", "series"
            ),
        ),
        ("plot_bar", lambda: visualization.plot_bar(["a", "b"], [1, 2], "bars")),
        ("plot_line", lambda: visualization.plot_line([1, 2], [3, 4], "lines")),
        ("plot_hourly_profile", lambda: visualization.plot_hourly_profile(_hourly_df())),
        ("plot_monthly_trend", lambda: visualization.plot_monthly_trend(_monthly_df())),
        ("plot_submetering", lambda: visualization.plot_submetering(_submetering_df())),
        (
            "plot_correlation_heatmap",
            lambda: visualization.plot_correlation_heatmap(_corr_df()),
        ),
        (
            "plot_histogram",
            lambda: visualization.plot_histogram(
                pd.Series(np.random.default_rng(42).normal(size=100), name="v")
            ),
        ),
        (
            "plot_box",
            lambda: visualization.plot_box(pd.Series([1.0, 2.0, 3.0], name="v")),
        ),
        (
            "plot_scatter",
            lambda: visualization.plot_scatter(
                pd.DataFrame({"x": range(10), "y": range(10)}), "x", "y"
            ),
        ),
    ],
    ids=[
        "plot_time_series",
        "plot_bar",
        "plot_line",
        "plot_hourly_profile",
        "plot_monthly_trend",
        "plot_submetering",
        "plot_correlation_heatmap",
        "plot_histogram",
        "plot_box",
        "plot_scatter",
    ],
)
def test_plot_returns_figure_with_nonzero_data(name, builder) -> None:
    fig = builder()
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0


def test_plot_time_series_data_present_and_sorted() -> None:
    df = pd.DataFrame({"t": [3, 1, 2], "v": [30, 10, 20]})
    fig = visualization.plot_time_series(df, "t", "v", "title")
    assert list(fig.data[0].x) == [1, 2, 3]
    assert list(fig.data[0].y) == [10, 20, 30]


def test_plot_scatter_respects_sample_cap() -> None:
    rng = np.random.default_rng(42)
    df = pd.DataFrame({"x": rng.normal(size=200), "y": rng.normal(size=200)})
    fig = visualization.plot_scatter(df, "x", "y", sample=50)
    assert len(fig.data[0].x) == 50


@pytest.mark.parametrize(
    "bad_df",
    [None, pd.DataFrame(), pd.DataFrame({"other": [1]})],
    ids=["none", "empty", "missing-columns"],
)
def test_plot_time_series_empty_input_is_placeholder(bad_df) -> None:
    fig = visualization.plot_time_series(bad_df, "t", "v", "empty")
    assert isinstance(fig, go.Figure)


@pytest.mark.parametrize(
    ("name", "builder"),
    [
        ("plot_hourly_profile", lambda: visualization.plot_hourly_profile(None)),
        ("plot_monthly_trend", lambda: visualization.plot_monthly_trend(pd.DataFrame())),
        ("plot_submetering", lambda: visualization.plot_submetering(pd.DataFrame())),
        (
            "plot_correlation_heatmap",
            lambda: visualization.plot_correlation_heatmap(pd.DataFrame()),
        ),
        ("plot_histogram", lambda: visualization.plot_histogram(None)),
        ("plot_box", lambda: visualization.plot_box(pd.Series(dtype=float))),
        (
            "plot_scatter",
            lambda: visualization.plot_scatter(pd.DataFrame(), "x", "y"),
        ),
    ],
    ids=[
        "plot_hourly_profile",
        "plot_monthly_trend",
        "plot_submetering",
        "plot_correlation_heatmap",
        "plot_histogram",
        "plot_box",
        "plot_scatter",
    ],
)
def test_empty_inputs_return_placeholder_figure(name, builder) -> None:
    fig = builder()
    assert isinstance(fig, go.Figure)


def test_plot_bar_labels_applied() -> None:
    fig = visualization.plot_bar(
        ["a"], [1], "title", labels={"x": "X axis", "y": "Y axis"}
    )
    assert fig.layout.xaxis.title.text == "X axis"
    assert fig.layout.yaxis.title.text == "Y axis"


# ---------------------------------------------------------------------------
# recommend_chart_types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("type_a", "type_b", "expected"),
    [
        ("numeric", None, ["histogram", "box"]),
        ("categorical", None, ["bar"]),
        ("datetime", None, ["line"]),
        ("numeric", "numeric", ["scatter", "histogram"]),
        ("numeric", "datetime", ["line", "scatter"]),
        ("numeric", "categorical", ["box", "bar"]),
        ("categorical", "categorical", ["bar"]),
        ("datetime", "datetime", ["line"]),
        ("categorical", "datetime", []),
        ("identifier", None, []),
        ("text", None, []),
        ("identifier", "numeric", []),
        ("text", "numeric", []),
        ("bogus", None, []),
        ("numeric", "bogus", []),
    ],
)
def test_recommend_chart_types(type_a, type_b, expected) -> None:
    assert visualization.recommend_chart_types(type_a, type_b) == expected


# ---------------------------------------------------------------------------
# figure_to_bytes
# ---------------------------------------------------------------------------


def test_figure_to_bytes_returns_bytes() -> None:
    fig = visualization.plot_bar(["a"], [1], "title")
    out = visualization.figure_to_bytes(fig, fmt="png")
    assert isinstance(out, bytes)


def test_figure_to_bytes_empty_figure_returns_bytes() -> None:
    out = visualization.figure_to_bytes(go.Figure(), fmt="svg")
    assert isinstance(out, bytes)
